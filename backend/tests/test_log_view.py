"""The log of this run inside the app (item 56): the ring buffer, the endpoint, the batched stream, and what a phone doesn't get."""

import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from pitchcontrol import logsetup
from pitchcontrol.config.models import NetworkSettings
from pitchcontrol.engine.engine import Engine
from pitchcontrol.logsetup import LOG_CAPACITY, MemoryLogHandler, memory_log, setup_logging
from pitchcontrol.menu import MenuActions, items_by_id, menu_json, native_menu
from pitchcontrol.server import app as app_module
from pitchcontrol.server.app import create_app

PHONE = ("192.168.1.50", 50000)


@pytest.fixture
def buffer():
    """A handler on the root logger for the test (the pytest log capture stays as it is)."""
    handler = MemoryLogHandler(capacity=50)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)  # not DEBUG: asyncio logs its own debug lines under the test client
    yield handler
    root.removeHandler(handler)
    root.setLevel(old_level)


@pytest.fixture
def engine(store):
    return Engine(store, enable_hardware=False)


def local(engine, buffer) -> TestClient:
    return TestClient(create_app(engine, log_buffer=buffer), client=("127.0.0.1", 50000))


def phone(store, buffer) -> TestClient:
    store.settings = store.settings.model_copy(update={"network": NetworkSettings(enabled=True)})
    return TestClient(create_app(Engine(store, enable_hardware=False), log_buffer=buffer), client=PHONE)


def texts(ws, count):
    """The next ``count`` text messages on the socket, as JSON (the engine state flows in between)."""
    return [json.loads(ws.receive()["text"]) for _ in range(count) if True]


def next_log(ws, limit=300):
    """The next batch of log records on the socket (the state messages in between are skipped)."""
    for _ in range(limit):
        message = ws.receive()
        if message.get("text"):
            body = json.loads(message["text"])
            if body.get("type") == "log":
                return body
    raise AssertionError("no log message")


# ------------------------------------------------------------------ the ring buffer


def test_records_carry_their_level_time_logger_and_message(buffer):
    before = time.time()
    logging.getLogger("pitchcontrol.test").warning("fixture %s is %d", "Bar", 3)
    (record,) = buffer.since()
    assert record["level"] == "WARNING"  # a field, not parsed from text
    assert record["logger"] == "pitchcontrol.test"
    assert record["msg"] == "fixture Bar is 3"
    assert before - 1 <= record["t"] <= time.time() + 1
    assert record["seq"] == 1


def test_every_level_is_kept_with_its_name(buffer):
    log = logging.getLogger("pitchcontrol.levels")
    log.setLevel(logging.DEBUG)
    log.debug("d")
    log.info("i")
    log.warning("w")
    log.error("e")
    log.critical("c")
    assert [r["level"] for r in buffer.since()] == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def test_an_exception_comes_with_its_traceback(buffer):
    try:
        raise ValueError("no such channel")
    except ValueError:
        logging.getLogger("pitchcontrol.tb").exception("write failed")
    (record,) = buffer.since()
    assert record["level"] == "ERROR"
    assert record["msg"].startswith("write failed\nTraceback")
    assert record["msg"].endswith("ValueError: no such channel")


def test_the_buffer_keeps_the_last_records_only(buffer):
    log = logging.getLogger("pitchcontrol.ring")
    for n in range(80):
        log.info("line %d", n)
    records = buffer.since()
    assert len(records) == 50 == buffer.capacity
    assert records[0]["msg"] == "line 30" and records[-1]["msg"] == "line 79"
    assert [r["seq"] for r in records] == list(range(31, 81))  # the numbers keep counting
    assert buffer.last_seq == 80


def test_since_gives_what_is_newer(buffer):
    log = logging.getLogger("pitchcontrol.since")
    for n in range(10):
        log.info("line %d", n)
    assert [r["msg"] for r in buffer.since(7)] == ["line 7", "line 8", "line 9"]  # numbers 8, 9, 10
    assert buffer.since(10) == [] and buffer.since(99) == []
    assert [r["msg"] for r in buffer.since(2, limit=3)] == ["line 2", "line 3", "line 4"]
    assert len(buffer.since(-5)) == 10


def test_setup_logging_attaches_a_fresh_buffer_per_run(tmp_path):
    root = logging.getLogger()
    saved_handlers, saved_level, saved_memory = root.handlers[:], root.level, memory_log()
    try:
        setup_logging(tmp_path / "logs")
        first = memory_log()
        assert first is not saved_memory and first in root.handlers
        logging.getLogger("pitchcontrol.run").error("boom")
        records = first.since()
        assert records[0]["msg"].startswith("logging to ")  # the run's first line
        assert [r["msg"] for r in records if r["logger"] == "pitchcontrol.run"] == ["boom"]
        setup_logging(tmp_path / "logs2")
        assert memory_log() is not first
        assert first not in root.handlers and memory_log() in root.handlers
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)
        logsetup._memory = saved_memory


def test_the_default_capacity_is_a_few_thousand():
    assert 2000 <= LOG_CAPACITY <= 10000 and MemoryLogHandler().capacity == LOG_CAPACITY


# ------------------------------------------------------------------ the endpoint


def test_the_endpoint_gives_the_buffer_and_what_is_newer(engine, buffer):
    log = logging.getLogger("pitchcontrol.api")
    log.error("first")
    log.info("second")
    client = local(engine, buffer)
    body = client.get("/api/log").json()
    assert [(r["level"], r["msg"]) for r in body["records"] if r["logger"] == "pitchcontrol.api"] == [("ERROR", "first"), ("INFO", "second")]
    assert body["last"] >= 2 and body["capacity"] == 50
    newer = client.get("/api/log", params={"after": 1}).json()["records"]
    assert [r["msg"] for r in newer if r["logger"] == "pitchcontrol.api"] == ["second"]  # (the HTTP client logs its own request too)


# ------------------------------------------------------------------ the stream


def test_the_stream_sends_the_history_then_new_records_in_batches(engine, buffer, monkeypatch):
    monkeypatch.setattr(app_module, "LOG_BATCH_SECONDS", 0.1)
    log = logging.getLogger("pitchcontrol.stream")
    log.warning("before")
    with local(engine, buffer).websocket_connect("/ws") as ws:
        ws.send_json({"type": "log_subscribe", "after": 0})
        first = next_log(ws)
        assert [r["msg"] for r in first["records"]] == ["before"] and "reset" not in first
        # a burst goes out together, not as one message per record
        for n in range(20):
            log.error("burst %d", n)
        got, batches = [], 0
        while len(got) < 20:
            batch = next_log(ws)
            batches += 1
            got += batch["records"]
        assert [r["msg"] for r in got] == [f"burst {n}" for n in range(20)]
        assert all(r["level"] == "ERROR" for r in got)
        assert batches < 5


def test_a_batch_is_capped_and_the_rest_follows(engine, buffer, monkeypatch):
    monkeypatch.setattr(app_module, "LOG_BATCH_SECONDS", 0.02)
    monkeypatch.setattr(app_module, "LOG_BATCH_MAX", 7)
    for n in range(20):
        logging.getLogger("pitchcontrol.cap").info("line %d", n)
    with local(engine, buffer).websocket_connect("/ws") as ws:
        ws.send_json({"type": "log_subscribe", "after": 0})
        sizes, msgs = [], []
        while len(msgs) < 20:
            batch = next_log(ws)
            sizes.append(len(batch["records"]))
            msgs += [r["msg"] for r in batch["records"]]
        assert sizes == [7, 7, 6] and msgs == [f"line {n}" for n in range(20)]


def test_subscribing_after_a_number_sends_only_what_is_newer(engine, buffer, monkeypatch):
    monkeypatch.setattr(app_module, "LOG_BATCH_SECONDS", 0.05)
    for n in range(5):
        logging.getLogger("pitchcontrol.after").info("line %d", n)
    with local(engine, buffer).websocket_connect("/ws") as ws:
        ws.send_json({"type": "log_subscribe", "after": 3})
        assert [r["msg"] for r in next_log(ws)["records"]] == ["line 3", "line 4"]


def test_a_number_ahead_of_this_run_resets_the_view(engine, buffer, monkeypatch):
    """The server was restarted while a browser tab stayed open: its last number means nothing in the new run."""
    monkeypatch.setattr(app_module, "LOG_BATCH_SECONDS", 0.05)
    logging.getLogger("pitchcontrol.reset").info("new run")
    with local(engine, buffer).websocket_connect("/ws") as ws:
        ws.send_json({"type": "log_subscribe", "after": 5000})
        batch = next_log(ws)
        assert batch["reset"] is True and [r["msg"] for r in batch["records"]] == ["new run"]


def test_nothing_is_sent_until_subscribed_or_after_unsubscribing(engine, buffer, monkeypatch):
    monkeypatch.setattr(app_module, "LOG_BATCH_SECONDS", 0.02)
    log = logging.getLogger("pitchcontrol.quiet")
    log.info("hello")
    with local(engine, buffer).websocket_connect("/ws") as ws:
        for _ in range(20):  # the engine state flows, no log
            assert "\"log\"" not in (ws.receive().get("text") or "")
        ws.send_json({"type": "log_subscribe", "after": 0})
        next_log(ws)
        ws.send_json({"type": "log_unsubscribe"})
        time.sleep(0.3)  # a batch already on its way may still arrive; after that none
        for _ in range(5):
            ws.receive()
        log.info("later")
        time.sleep(0.2)
        for _ in range(40):
            assert "later" not in (ws.receive().get("text") or "")


# ------------------------------------------------------------------ a device on the network


def test_a_phone_gets_no_log(store, buffer):
    logging.getLogger("pitchcontrol.private").error(r"can't open C:\Users\someone\data")
    device = phone(store, buffer)
    assert device.get("/api/state").status_code == 200  # on the network, otherwise
    answer = device.get("/api/log")
    assert answer.status_code == 403
    assert "someone" not in answer.text
    assert device.get("/api/app-info").json()["local"] is False  # Settings draws no Log section for it (LogSection.tsx)


def test_a_phone_that_asks_for_the_stream_gets_nothing(store, buffer, monkeypatch):
    monkeypatch.setattr(app_module, "LOG_BATCH_SECONDS", 0.02)
    logging.getLogger("pitchcontrol.private").error(r"can't open C:\Users\someone\data")
    with phone(store, buffer).websocket_connect("/ws") as ws:
        ws.send_json({"type": "log_subscribe", "after": 0})
        time.sleep(0.2)
        for _ in range(40):
            text = ws.receive().get("text") or ""
            assert "someone" not in text and '"records"' not in text


# ------------------------------------------------------------------ Help → Show log


def test_help_show_log_is_in_the_menu():
    item = items_by_id()["help.log"]
    assert (item.label, item.kind) == ("Show log", "ui")  # the page opens Settings at the log panel (App.tsx: runMenu)
    help_menu = next(m for m in menu_json("win") if m["title"] == "Help")
    assert {"id": "help.log", "label": "Show log", "kind": "ui", "key": ""} in help_menu["items"]


def test_the_native_menu_asks_the_page_to_show_the_log():
    from webview.menu import MenuAction

    class Window:
        def __init__(self):
            self.js = []

        def evaluate_js(self, code):
            self.js.append(code)

    window = Window()
    help_menu = next(m for m in native_menu(MenuActions("/d", "/l", window=window)) if m.title == "Help")
    show = next(i for i in help_menu.items if isinstance(i, MenuAction) and i.title == "Show log")
    show.function()
    assert window.js == ["window.pitchMenu && window.pitchMenu('help.log')"]
