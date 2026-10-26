"""Background writer threads: the engine hands over the latest frame and never blocks on I/O."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import serial

from .. import activity
from ..config.models import DeviceRef
from .devices import resolve_port

log = logging.getLogger(__name__)

TIMING_SUMMARY_S = 10.0  # one summary line per this many seconds
TIMING_LATE_FACTOR = 1.5  # a frame is late when its gap to the previous one is over this x the target frame time (item 98: was 2.0)


class FrameTimingLog:
    """The opt-in timing log of a writer (Open DMX, "Log frame timing"): per frame the start, the end, the
    gap to the previous frame (start to start, so it compares with the target frame time) and the frames the
    worker dropped; one summary line every TIMING_SUMMARY_S and one line per late frame. Only the writer's
    thread calls frame(); dropped is counted by LatestFrameWorker.submit."""

    def __init__(
        self, name: str, engine_period: Callable[[], float], min_period: float = 0.0, activities: activity.ActivityRecorder = activity.ACTIVITIES
    ) -> None:
        self.name = name
        self.activities = activities  # what ran at the time of a late frame (item 98)
        self.engine_period = engine_period  # the engine's frame time in seconds, read live
        self.min_period = min_period  # the writer's own floor (an Open DMX sends at most 30 fps, item 35)
        self.dropped = 0  # frames replaced before the writer took them, since the last summary
        self._origin: float | None = None  # the first frame's start: the times in the lines are seconds after it
        self._prev_start: float | None = None
        self._window_start = 0.0
        self._frames = 0
        self._longest_write = 0.0
        self._largest_gap = 0.0
        self._late = 0
        self._dropped_at_last_frame = 0

    def target_period(self) -> float:
        """What a frame should take: the engine's frame time, or the writer's floor when that is longer."""
        return max(self.engine_period(), self.min_period)

    def reset(self) -> None:
        """After an error or a reconnect: the next gap would only measure the outage."""
        self._prev_start = None

    def frame(self, start: float, end: float) -> None:
        if self._origin is None:
            self._origin = self._window_start = start
        prev_start = self._prev_start
        gap = start - prev_start if prev_start is not None else None
        self._prev_start = start
        write = end - start
        self._frames += 1
        self._longest_write = max(self._longest_write, write)
        if gap is not None:
            self._largest_gap = max(self._largest_gap, gap)
            period = self.target_period()
            if gap > TIMING_LATE_FACTOR * period:
                self._late += 1
                meanwhile = activity.format_summary(self.activities.overlapping(prev_start, end))  # item 98
                log.info(
                    "%s: late frame: gap %.1f ms (target %.1f ms), write %.1f ms (start +%.3f s, end +%.3f s), %d dropped since the last frame; meanwhile: %s",
                    self.name, gap * 1000, period * 1000, write * 1000,
                    start - self._origin, end - self._origin, self.dropped - self._dropped_at_last_frame, meanwhile,
                )
        self._dropped_at_last_frame = self.dropped
        elapsed = end - self._window_start
        if elapsed >= TIMING_SUMMARY_S:
            target = f"{1 / self.target_period():.1f}"
            if self.engine_period() < self.min_period:
                target += f", clamped from {1 / self.engine_period():.1f}"  # the dropped frames are the ones the clamp skipped (item 35)
            gen2 = next((s for s in self.activities.overlapping(self._window_start, end) if s.label == "gc gen2"), None)
            gc_text = f", gc gen2 {gen2.count} (longest {gen2.longest_s * 1000:.0f} ms)" if gen2 is not None else ""  # item 98
            log.info(
                "%s: timing, last %.1f s: %.1f fps (target %s), longest write %.1f ms, largest gap %.1f ms, late frames %d, dropped %d%s",
                self.name, elapsed, self._frames / elapsed, target, self._longest_write * 1000,
                self._largest_gap * 1000, self._late, self.dropped, gc_text,
            )
            self._window_start, self._frames = end, 0
            self._longest_write = self._largest_gap = 0.0
            self._late = self.dropped = self._dropped_at_last_frame = 0


class LatestFrameWorker:
    """Keeps only the newest submitted frame and writes it from its own thread."""

    name = "output"
    min_interval = 0.0  # seconds: the least time between the starts of two writes (0: as fast as frames come), item 35

    def __init__(self) -> None:
        self._last_start = float("-inf")  # when the last write started (perf_counter: monotonic() ticks in 15.6 ms steps on Windows with Python 3.12, item 35)
        self._frame: object | None = None
        self._event = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self.connected = False
        self.last_error: str | None = None
        self.frames_sent = 0
        self.timing: FrameTimingLog | None = None  # set before start() to log the timing of each frame
        self._pending = False  # a submitted frame the thread has not taken yet (only kept while timing is on)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._event.set()
        self._thread.join(timeout=2)
        self.close()

    def submit(self, frame: object) -> None:
        timing = self.timing
        if timing is not None:
            if self._pending:
                timing.dropped += 1  # the thread never wrote the frame this one replaces
            self._pending = True
        self._frame = frame
        self._event.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._event.wait(timeout=0.5)
            if self.min_interval > 0:
                # a minimum gap between starts, kept before the frame is read so the one written is the newest (item 35)
                remaining = self._last_start + self.min_interval - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)  # not Event.wait: on Windows it waits in 15.6 ms timer steps; the remainder is at most ~33 ms, so stopping stays responsive (item 35)
                    if self._stop.is_set():
                        break
            self._event.clear()
            timing = self.timing
            if timing is not None:
                self._pending = False  # before the frame is read: a submit in between counts as fresh
            frame = self._frame
            if frame is None or self._stop.is_set():
                continue
            try:
                if not self.connected:
                    with activity.track(f"open {self.name}"):  # item 98
                        self.open()
                start = self._last_start = time.perf_counter()
                self.write(frame)
                if timing is not None:
                    timing.frame(start, time.perf_counter())
                self.frames_sent += 1
            except Exception as exc:  # noqa: BLE001 - hardware errors must never kill the thread
                if self.connected or self.last_error != str(exc):
                    log.warning("%s: %s", self.name, exc)
                self.last_error = str(exc)
                self.close()
                if timing is not None:
                    timing.reset()
                time.sleep(1.0)  # retry rate while the device is missing

    def status(self) -> dict:
        return {"connected": self.connected, "error": self.last_error, "frames": self.frames_sent}

    # -- to implement
    def open(self) -> None:
        self.connected = True

    def write(self, frame: object) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self.connected = False


class SerialWorker(LatestFrameWorker):
    def __init__(self, ref: DeviceRef, baudrate: int, name: str) -> None:
        self.name = name
        self.ref = ref
        self.baudrate = baudrate
        self.port: serial.Serial | None = None
        super().__init__()

    def open(self) -> None:
        path = resolve_port(self.ref)
        if not path:
            raise ConnectionError("device not found (check Connections)")
        self.port = serial.Serial(path, self.baudrate, timeout=0, write_timeout=1)
        self.connected = True
        self.last_error = None
        log.info("%s: opened %s at %d baud", self.name, path, self.baudrate)

    def write(self, frame: object) -> None:
        assert self.port is not None and isinstance(frame, (bytes, bytearray))
        self.port.write(frame)

    def close(self) -> None:
        if self.port is not None:
            try:
                self.port.close()
            except Exception:  # noqa: BLE001
                pass
        self.port = None
        self.connected = False


DMX_BAUD = 250000
OPEN_DMX_MAX_FPS = 30  # a 512-slot frame is 22.6 ms on the wire, plus the break and the driver's calls: at 40 fps the next break came while the FTDI chip still sent the end of the last frame (the "31 ms a write" logged on Windows was rounded to its 15.6 ms clock steps, item 35)
DMX_BYTE_S = 11 / DMX_BAUD  # one slot on the wire: start bit, 8 data bits, 2 stop bits at 250 kbaud (44 us)
WIRE_MARGIN_S = 0.002  # on top of the bytes' time: the USB latency and the FTDI chip's first byte (item 35)
DMX_BREAK_BAUD = 90000  # one 0x00 byte (start + 8 zero bits, 9 x 11.1 us) is a 100 us break, the 2 stop bits a 22 us mark


class OpenDmxWorker(SerialWorker):
    """Enttec Open DMX USB and other bare FTDI RS-485 dongles: no processor, so we make the DMX
    signal ourselves, 250 kbaud 8N2: a break, a mark after break, the start code 0 and up to 512
    channels. The frame is the universe (bytes).

    What works on macOS with the FTDI serial driver (tools/open_dmx_probe.py, 2026-10-11):
    RTS and DTR low (the RS-485 driver follows them: with the system default, high, the port
    transmits and the fixture sees nothing), and a drain (tcdrain) between the steps. The break is
    one 0x00 byte at 90000 baud. Left as it is, a break set by the "break" method can stay on
    until the interface is unplugged and holds all output."""

    # an engine at 30 fps hands over a frame every 33.3 ms with some jitter: a gap of exactly 1/30 s would make a frame
    # that comes 1 ms early wait and the next one be dropped. The wire guard in write(), not this gap, keeps the break
    # off the end of the previous frame (item 35)
    min_interval = 1 / OPEN_DMX_MAX_FPS - 0.0015

    BREAK_S = 0.002  # the break line method: at least 88 us; USB moves in 1 ms steps, up to 1 s is allowed
    MARK_S = 0.002

    def __init__(self, ref: DeviceRef, name: str, break_method: str = "baud") -> None:
        super().__init__(ref, DMX_BAUD, name)
        self.break_method = break_method
        self._wire_free_at = 0.0  # perf_counter time by which the last frame's bytes have left the FTDI chip (item 35)

    def open(self) -> None:
        path = resolve_port(self.ref)
        if not path:
            raise ConnectionError("device not found (check Connections)")
        self.port = serial.Serial(
            path, DMX_BAUD, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_TWO,
            timeout=0, write_timeout=1,
        )
        try:
            self.port.break_condition = False  # a break left on by an earlier run holds all output
        except (OSError, serial.SerialException):
            pass
        self.port.rts = False
        self.port.dtr = False
        time.sleep(0.02)
        self._wire_free_at = 0.0
        self.connected = True
        self.last_error = None
        log.info("%s: opened %s as Open DMX (%d baud, 8N2, RTS / DTR low, break by %s)", self.name, path, DMX_BAUD, self.break_method)

    def status(self) -> dict:
        return {**super().status(), "max_fps": OPEN_DMX_MAX_FPS}

    def write(self, frame: object) -> None:
        assert self.port is not None and isinstance(frame, (bytes, bytearray))
        port = self.port
        # flush() returns when the driver has handed the bytes to the chip, which still holds up to 256 of them (~11 ms): a break
        # now would cut into the end of the last frame, so wait until its bytes can have left (item 35)
        wait = self._wire_free_at - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        port.flush()  # the previous frame has left (the driver sends nothing without a drain)
        if self.break_method == "baud":
            port.baudrate = DMX_BREAK_BAUD
            port.write(b"\x00")  # start + 8 zero bits at 90000 baud: a 100 us break, then 2 stop bits
            port.flush()
            # the same as for the frame: flush() returns before the chip has sent the byte, and switching back now would
            # send it at 250 kbaud, a 36 us break that receivers don't take for one (item 35)
            time.sleep(WIRE_MARGIN_S)
            port.baudrate = DMX_BAUD
        else:
            port.break_condition = True
            time.sleep(self.BREAK_S)
            port.break_condition = False
            time.sleep(self.MARK_S)
        data = b"\x00" + bytes(frame[:512])
        self._wire_free_at = time.perf_counter() + len(data) * DMX_BYTE_S + WIRE_MARGIN_S
        port.write(data)
