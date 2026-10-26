"""The activity recorder and what the frame timing logs say with it (item 98)."""

import gc
import logging
import threading
import time
import types

from pitchcontrol import activity
from pitchcontrol.activity import ActivityRecorder, format_summary
from pitchcontrol.engine.perf import EngineTimingLog
from pitchcontrol.io.workers import FrameTimingLog


def by_label(summaries):
    return {s.label: s for s in summaries}


# ------------------------------------------------------------------ the recorder


def test_overlapping_aggregates_by_label():
    r = ActivityRecorder()
    r.record("write a.json", 10.0, 10.002)
    r.record("write a.json", 10.5, 10.505)
    r.record("gc gen2", 10.2, 10.284)
    got = by_label(r.overlapping(10.0, 11.0))
    assert got["write a.json"].count == 2
    assert abs(got["write a.json"].total_s - 0.007) < 1e-9
    assert abs(got["write a.json"].longest_s - 0.005) < 1e-9
    assert got["gc gen2"].count == 1 and not got["gc gen2"].running
    assert [s.label for s in r.overlapping(10.0, 11.0)] == ["gc gen2", "write a.json"]   # the longest total first


def test_overlapping_takes_what_touches_the_span_only():
    r = ActivityRecorder()
    r.record("before", 1.0, 2.0)
    r.record("across the start", 2.9, 3.1)
    r.record("inside", 3.2, 3.3)
    r.record("across the end", 3.9, 4.1)
    r.record("after", 5.0, 6.0)
    assert sorted(by_label(r.overlapping(3.0, 4.0))) == ["across the end", "across the start", "inside"]


def test_a_running_activity_overlaps_and_is_marked():
    r = ActivityRecorder()
    with r.track("audio device lookup"):
        got = by_label(r.overlapping(0.0, time.perf_counter() + 1))
        assert got["audio device lookup"].running and got["audio device lookup"].count == 1
        # started after the span: not part of it
        assert r.overlapping(0.0, 1.0) == []
    done = by_label(r.overlapping(0.0, time.perf_counter() + 1))
    assert not done["audio device lookup"].running and done["audio device lookup"].count == 1


def test_a_running_activity_counts_up_to_now():
    r = ActivityRecorder()
    token = r._begin("lookup", 100.0)
    s = by_label(r.overlapping(90.0, 101.0, now=101.6))["lookup"]
    assert s.running and abs(s.total_s - 1.6) < 1e-9
    r._end(token, 102.0)
    assert not by_label(r.overlapping(90.0, 101.0))["lookup"].running


def test_track_records_even_when_the_block_fails():
    r = ActivityRecorder()
    try:
        with r.track("boom"):
            raise ValueError
    except ValueError:
        pass
    assert by_label(r.overlapping(0.0, time.perf_counter() + 1))["boom"].count == 1
    assert r._running == {}


def test_the_ring_forgets_what_is_older_than_its_window():
    r = ActivityRecorder(keep_s=60.0)
    r.record("old", 0.0, 1.0)
    r.record("recent", 50.0, 51.0)
    r.record("now", 70.0, 70.5)          # 'old' ended more than 60 s before this
    assert sorted(by_label(r.overlapping(0.0, 100.0))) == ["now", "recent"]


def test_the_ring_is_capped_in_size():
    r = ActivityRecorder(max_entries=50)
    for i in range(500):
        r.record("x", i * 0.01, i * 0.01 + 0.001)
    assert len(r._done) == 50
    assert by_label(r.overlapping(0.0, 10.0))["x"].count == 50   # the newest ones


def test_recording_from_several_threads_loses_nothing():
    r = ActivityRecorder(max_entries=100000)

    def work():
        for i in range(500):
            now = time.perf_counter()
            r.record("t", now, now + 0.001)
            with r.track("u"):
                pass

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    got = by_label(r.overlapping(0.0, time.perf_counter() + 1))
    assert got["t"].count == 2000 and got["u"].count == 2000
    assert r._running == {}


def test_record_nowait_never_waits_for_the_lock_and_keeps_the_event():
    r = ActivityRecorder()
    r.record_nowait("a", 1.0, 2.0)
    with r._lock:                        # the holder is this thread, like a collection started inside record()
        r.record_nowait("b", 1.0, 2.5)   # must return at once, not wait for itself
    assert sorted(by_label(r.overlapping(0.0, 3.0))) == ["a", "b"]  # "b" joined the ring at the query


# ------------------------------------------------------------------ the text


def test_format_summary():
    r = ActivityRecorder()
    r.record("gc gen2", 1.0, 1.084)
    r.record("write macros.json", 1.1, 1.102)
    r.record("write macros.json", 1.2, 1.201)
    r.record("gc gen2", 1.3, 1.3)        # under half a millisecond
    token = r._begin("audio device lookup", 0.5)
    text = format_summary(r.overlapping(1.0, 2.0, now=2.1))
    r._end(token, 3.0)
    assert "gc gen2 2× 84 ms (longest 84 ms)" in text
    assert "write macros.json 2× 3 ms (longest 2 ms)" in text
    assert "audio device lookup 1× 1.6 s (running)" in text
    assert format_summary([]) == "nothing recorded"


def test_format_summary_single_event():
    r = ActivityRecorder()
    r.record("midi device scan", 1.0, 1.0001)
    assert format_summary(r.overlapping(0.0, 2.0)) == "midi device scan 1× <1 ms"


# ------------------------------------------------------------------ the garbage collector


def test_the_gc_hook_records_a_full_collection_as_gen2():
    activity.install_gc_hook()
    activity.install_gc_hook()           # twice is the same as once
    try:
        assert gc.callbacks.count(activity._gc_callback) == 1
        t0 = time.perf_counter()
        gc.collect()
        got = by_label(activity.overlapping(t0 - 0.001, time.perf_counter() + 1))
        assert got["gc gen2"].count >= 1
    finally:
        activity.remove_gc_hook()
    assert activity._gc_callback not in gc.callbacks
    activity.remove_gc_hook()            # and removing twice is harmless


def test_the_gc_hook_skips_short_gen0_collections(monkeypatch):
    rec = ActivityRecorder()
    monkeypatch.setattr(activity, "ACTIVITIES", rec)
    clock = iter([10.0, 10.001, 20.0, 20.01, 30.0, 30.0001])
    monkeypatch.setattr(activity, "time", types.SimpleNamespace(perf_counter=lambda: next(clock)))   # only the hook sees this clock
    activity._gc_callback("start", {"generation": 0})
    activity._gc_callback("stop", {"generation": 0})      # 1 ms: not worth a place
    activity._gc_callback("start", {"generation": 0})
    activity._gc_callback("stop", {"generation": 0})      # 10 ms: kept
    activity._gc_callback("start", {"generation": 1})
    activity._gc_callback("stop", {"generation": 1})      # gen1 is always kept, however short
    assert sorted((s.label, s.count) for s in rec.overlapping(0.0, 100.0, now=100.0)) == [("gc gen0", 1), ("gc gen1", 1)]


# ------------------------------------------------------------------ the files


def test_write_json_is_recorded(tmp_path):
    from pitchcontrol.config.loader import write_json

    t0 = time.perf_counter()
    write_json(tmp_path / "macros.json", {"a": 1})
    got = by_label(activity.overlapping(t0 - 0.001, time.perf_counter() + 1))
    assert got["write macros.json"].count >= 1


# ------------------------------------------------------------------ the writer's late line


def _info(caplog, kind):
    return [r.getMessage() for r in caplog.records if kind in r.getMessage()]


def test_the_late_threshold_is_one_and_a_half_frames(caplog):
    caplog.set_level(logging.INFO)
    t = FrameTimingLog("opendmx1", lambda: 0.025, activities=ActivityRecorder())
    t.frame(10.0, 10.004)
    t.frame(10.0365, 10.04)              # 36.5 ms: under 1.5 x 25 ms
    assert _info(caplog, "late frame:") == []
    t.frame(10.0365 + 0.0385, 10.08)     # 38.5 ms: over
    assert len(_info(caplog, "late frame:")) == 1


def test_the_late_line_says_what_ran_meanwhile(caplog):
    caplog.set_level(logging.INFO)
    rec = ActivityRecorder()
    t = FrameTimingLog("opendmx1", lambda: 0.025, activities=rec)
    t.frame(10.0, 10.004)
    t.frame(10.025, 10.029)
    rec.record("gc gen2", 10.05, 10.134)
    rec.record("write macros.json", 10.06, 10.063)
    rec.record("elsewhere", 12.0, 12.5)
    t.frame(10.140, 10.144)              # gap 115 ms
    late = _info(caplog, "late frame:")
    assert len(late) == 1
    assert "; meanwhile: gc gen2 1× 84 ms, write macros.json 1× 3 ms" in late[0]
    assert "elsewhere" not in late[0]


def test_the_late_line_with_nothing_recorded(caplog):
    caplog.set_level(logging.INFO)
    t = FrameTimingLog("opendmx1", lambda: 0.025, activities=ActivityRecorder())
    t.frame(10.0, 10.004)
    t.frame(10.2, 10.204)
    assert _info(caplog, "late frame:")[0].endswith("meanwhile: nothing recorded")


def test_the_summary_names_the_gen2_collections_of_the_window(caplog):
    caplog.set_level(logging.INFO)
    rec = ActivityRecorder()
    t = FrameTimingLog("opendmx1", lambda: 0.025, activities=rec)
    rec.record("gc gen2", 103.0, 103.040)
    rec.record("gc gen2", 105.0, 105.084)
    rec.record("gc gen1", 106.0, 106.002)
    for i in range(402):
        t.frame(100.0 + 0.025 * i, 100.0 + 0.025 * i + 0.005)
    summary = _info(caplog, "timing,")
    assert len(summary) == 1 and summary[0].endswith(", dropped 0, gc gen2 2 (longest 84 ms)")
    for i in range(402, 805):            # the next window had none: nothing is added
        t.frame(100.0 + 0.025 * i, 100.0 + 0.025 * i + 0.005)
    summary = _info(caplog, "timing,")
    assert len(summary) == 2 and summary[1].endswith("dropped 0")


# ------------------------------------------------------------------ the engine's late frames


def test_the_engine_says_when_a_frame_was_late(caplog):
    caplog.set_level(logging.INFO)
    rec = ActivityRecorder()
    log = EngineTimingLog(lambda: 0.025, activities=rec)
    log.frame(5.0, 0.004)
    log.frame(5.025, 0.004)              # on time
    log.frame(5.0625 - 0.0001, 0.004)    # 37.4 ms: under 1.5 x 25 ms
    assert _info(caplog, "engine: late frame") == []
    rec.record("audio re-init", 5.07, 5.12)
    log.frame(5.2, 0.006)                # 137 ms
    late = _info(caplog, "engine: late frame")
    assert len(late) == 1
    assert late[0].startswith("engine: late frame: gap 137.6 ms (target 25.0 ms), tick 6.0 ms; meanwhile: ")
    assert "audio re-init 1× 50 ms" in late[0]


def test_a_long_engine_tick_is_recorded_for_the_writers_line(caplog):
    caplog.set_level(logging.INFO)
    rec = ActivityRecorder()
    log = EngineTimingLog(lambda: 0.025, activities=rec)
    log.frame(5.0, 0.004)
    assert rec.overlapping(0.0, 10.0) == []              # a short tick is not worth a place in the ring
    log.frame(5.025, 0.060)                              # over 1.5 x the period
    assert by_label(rec.overlapping(0.0, 10.0))["engine tick"].count == 1
    log.frame(5.1, 0.004)                                # the gap after it names the long tick
    assert "engine tick 1× 60 ms" in _info(caplog, "engine: late frame")[0]


def test_the_engine_summary_every_10_seconds(caplog):
    caplog.set_level(logging.INFO)
    log = EngineTimingLog(lambda: 0.025, activities=ActivityRecorder())
    for i in range(402):
        log.frame(100.0 + 0.025 * i + (0.020 if i >= 200 else 0.0), 0.012 if i == 100 else 0.004)
    summary = _info(caplog, "engine: timing,")
    assert len(summary) == 1
    assert "last 10.0 s" in summary[0] and "fps (target 40.0)" in summary[0]
    assert "longest tick 12.0 ms" in summary[0] and "largest gap 45.0 ms" in summary[0]
    assert "late frames 1" in summary[0]


def test_the_engine_log_starts_clean_after_a_reset(caplog):
    caplog.set_level(logging.INFO)
    log = EngineTimingLog(lambda: 0.025, activities=ActivityRecorder())
    log.frame(5.0, 0.004)
    log.reset()                          # the timing log was off for a while: the gap would only measure that
    log.frame(60.0, 0.004)
    assert _info(caplog, "engine: late frame") == []


def test_the_engine_loop_logs_only_while_an_output_has_timing_on(store, caplog):
    from pitchcontrol.engine.engine import Engine

    caplog.set_level(logging.INFO)
    engine = Engine(store, enable_hardware=False)
    calls = []
    engine.timing_log.frame = lambda start, tick_s: calls.append(start)
    engine.outputs.timing_on = lambda: False
    engine.start()
    time.sleep(0.15)
    engine.stop()
    assert calls == []
    engine.outputs.timing_on = lambda: True
    engine.start()
    time.sleep(0.15)
    engine.stop()
    assert calls                         # the loop fed the engine's timing log
    assert activity._gc_callback not in gc.callbacks   # start() installs the gc hook, stop() takes it out
