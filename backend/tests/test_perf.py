"""The frame times for the header's FPS bubble (item 66): the ring the engine writes, and the stream the bubble reads."""

import json
import time

from fastapi.testclient import TestClient

from pitchcontrol.engine.engine import Engine
from pitchcontrol.engine.perf import PERF_FRAMES, FrameTimes
from pitchcontrol.server import app as app_module
from pitchcontrol.server.app import create_app


# ------------------------------------------------------------------ the ring


def test_since_gives_the_frames_after_a_number_oldest_first():
    ft = FrameTimes(size=8)
    for n in range(5):
        ft.record(25.0 + n, 1.0 + n)
    assert ft.since(0) == (5, [[25.0, 1.0], [26.0, 2.0], [27.0, 3.0], [28.0, 4.0], [29.0, 5.0]])
    assert ft.since(3) == (5, [[28.0, 4.0], [29.0, 5.0]])
    assert ft.since(5) == (5, [])


def test_the_ring_keeps_the_last_frames_only():
    ft = FrameTimes(size=4)
    for n in range(10):
        ft.record(float(n), 0.0)
    count, rows = ft.since(0)
    assert count == 10
    assert [r[0] for r in rows] == [6.0, 7.0, 8.0, 9.0]


def test_a_limit_gives_the_newest_frames():
    ft = FrameTimes(size=16)
    for n in range(10):
        ft.record(float(n), 0.0)
    assert [r[0] for r in ft.since(0, limit=3)[1]] == [7.0, 8.0, 9.0]


def test_a_number_ahead_of_the_count_gives_everything():
    """The bubble stayed open over an engine restart: its last frame number is ahead of the new engine's."""
    ft = FrameTimes(size=8)
    ft.record(25.0, 1.0)
    assert ft.since(500) == (1, [[25.0, 1.0]])


def test_values_are_rounded_for_the_wire():
    ft = FrameTimes(size=4)
    ft.record(25.123456, 1.98765)
    assert ft.since(0)[1] == [[25.12, 1.99]]


def test_the_ring_covers_ten_seconds_at_any_frame_rate_settings_offers():
    assert PERF_FRAMES >= 10 * 100


def test_the_running_engine_records_one_entry_per_frame(store):
    engine = Engine(store, enable_hardware=False)
    engine.start()
    try:
        deadline = time.monotonic() + 3
        while engine.frame_times.count < 10 and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        engine.stop()
    count, rows = engine.frame_times.since(0)
    assert count >= 10 and abs(count - engine.frame) <= 1
    period = 1000 / store.settings.fps
    # after the first frame the intervals are about the target frame time; the compute time is part of it
    assert all(0 < interval < 10 * period for interval, _ in rows[1:])
    assert all(0 <= tick for _, tick in rows)


# ------------------------------------------------------------------ the stream


def next_perf(ws, limit=300):
    for _ in range(limit):
        message = ws.receive()
        if message.get("text"):
            body = json.loads(message["text"])
            if body.get("type") == "perf":
                return body
    raise AssertionError("no perf message")


def test_the_stream_sends_the_history_then_what_is_new(store, monkeypatch):
    monkeypatch.setattr(app_module, "PERF_SECONDS", 0.05)
    engine = Engine(store, enable_hardware=False)  # not started: the test writes the frames
    for _ in range(5):
        engine.frame_times.record(25.0, 2.0)
    with TestClient(create_app(engine)).websocket_connect("/ws?preview=0") as ws:
        ws.send_json({"type": "perf_subscribe"})
        first = next_perf(ws)
        assert first["frame"] == 5 and first["fps"] == store.settings.fps
        assert first["rows"] == [[25.0, 2.0]] * 5
        engine.frame_times.record(61.0, 3.0)
        rows = []
        while not rows:
            batch = next_perf(ws)
            rows = batch["rows"]
        assert batch["frame"] == 6 and rows == [[61.0, 3.0]]


def test_the_history_is_the_last_ten_seconds(store, monkeypatch):
    monkeypatch.setattr(app_module, "PERF_SECONDS", 0.05)
    engine = Engine(store, enable_hardware=False)
    for _ in range(PERF_FRAMES):
        engine.frame_times.record(25.0, 2.0)
    with TestClient(create_app(engine)).websocket_connect("/ws?preview=0") as ws:
        ws.send_json({"type": "perf_subscribe"})
        assert len(next_perf(ws)["rows"]) == int(10 * store.settings.fps) + 1


def test_nothing_is_sent_without_a_subscription_or_after_unsubscribing(store, monkeypatch):
    monkeypatch.setattr(app_module, "PERF_SECONDS", 0.02)
    engine = Engine(store, enable_hardware=False)
    with TestClient(create_app(engine)).websocket_connect("/ws?preview=0") as ws:
        for _ in range(3):  # the state flows, no perf message
            assert "type" not in json.loads(ws.receive()["text"])
        ws.send_json({"type": "perf_subscribe"})
        next_perf(ws)
        ws.send_json({"type": "perf_unsubscribe"})
        # what was on the way when it unsubscribed may still come: skip past three states (0.2 s), then none
        states = 0
        while states < 3:
            states += "type" not in json.loads(ws.receive()["text"])
        assert all(json.loads(ws.receive()["text"]).get("type") is None for _ in range(8))
