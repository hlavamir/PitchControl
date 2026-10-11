"""Background writer threads: the engine hands over the latest frame and never blocks on I/O."""

from __future__ import annotations

import logging
import threading
import time

import serial

from ..config.models import DeviceRef
from .devices import resolve_port

log = logging.getLogger(__name__)


class LatestFrameWorker:
    """Keeps only the newest submitted frame and writes it from its own thread."""

    name = "output"

    def __init__(self) -> None:
        self._frame: object | None = None
        self._event = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self.connected = False
        self.last_error: str | None = None
        self.frames_sent = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._event.set()
        self._thread.join(timeout=2)
        self.close()

    def submit(self, frame: object) -> None:
        self._frame = frame
        self._event.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._event.wait(timeout=0.5)
            self._event.clear()
            frame = self._frame
            if frame is None or self._stop.is_set():
                continue
            try:
                if not self.connected:
                    self.open()
                self.write(frame)
                self.frames_sent += 1
            except Exception as exc:  # noqa: BLE001 - hardware errors must never kill the thread
                if self.connected or self.last_error != str(exc):
                    log.warning("%s: %s", self.name, exc)
                self.last_error = str(exc)
                self.close()
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
            raise ConnectionError("device not found (check the Output page)")
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


def clear_modem_flow_control(port) -> str:
    """Switch off every hardware flow-control flag of a POSIX tty and say what was set.

    On macOS the tty can hold back output until a modem line is up (CTS, DSR, carrier); pyserial
    only clears RTS/CTS. A bare FTDI dongle has none of these lines wired, so a flag left on makes
    every write time out ("out_waiting" never goes down). Returns e.g. "CDSR_OFLOW CCAR_OFLOW"."""
    try:
        import termios
    except ImportError:  # Windows
        return ""
    fd = getattr(port, "fd", None)
    if fd is None:
        return ""
    names = ("CRTSCTS", "CCTS_OFLOW", "CRTS_IFLOW", "CDTR_IFLOW", "CDSR_OFLOW", "CCAR_OFLOW", "MDMBUF")
    attrs = termios.tcgetattr(fd)
    was = [n for n in names if getattr(termios, n, 0) and attrs[2] & getattr(termios, n)]
    mask = 0
    for n in names:
        mask |= getattr(termios, n, 0)
    if attrs[2] & mask:
        attrs[2] &= ~mask
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return " ".join(was)


DMX_BAUD = 250000
DMX_BREAK_BAUD = 90000  # one 0x00 byte (start + 8 zero bits, 9 x 11.1 us) is a 100 us break, the 2 stop bits a 22 us mark
DMX_BYTE_S = 11 / DMX_BAUD  # a slot is 1 start + 8 data + 2 stop bits = 44 us


class OpenDmxWorker(SerialWorker):
    """Enttec Open DMX USB and other bare FTDI RS-485 dongles: no processor, so we make the DMX
    signal ourselves, 250 kbaud 8N2: a break, a mark after break, the start code 0 and up to 512
    channels. The frame is the universe (bytes).

    The USB serial driver cannot be trusted to say when the chip has really sent something
    (tcdrain returns early), and a baud rate change is a separate USB transfer that may overtake
    data already queued. So the timing is ours: we wait for the previous frame by its length, and
    after every step (baud rate, break byte) we wait for it to have taken effect."""

    BREAK_S = 0.002  # the break line method: at least 88 us; USB moves in 1 ms steps, up to 1 s is allowed
    MARK_S = 0.002
    SETTLE_S = 0.002  # baud rate method: time for one USB transfer to take effect

    def __init__(self, ref: DeviceRef, name: str, break_method: str = "baud") -> None:
        super().__init__(ref, DMX_BAUD, name)
        self.break_method = break_method
        self._busy_until = 0.0

    def open(self) -> None:
        path = resolve_port(self.ref)
        if not path:
            raise ConnectionError("device not found (check the Output page)")
        self.port = serial.Serial(
            path, DMX_BAUD, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_TWO,
            timeout=0, write_timeout=1,
        )
        # RTS / DTR / the output buffer are left as the system opened the port (forcing the lines low
        # made every write time out on macOS); the hardware flow-control flags are switched off
        flags = clear_modem_flow_control(self.port)
        if flags:
            log.info("%s: switched off the flow-control flags %s", self.name, flags)
        time.sleep(0.02)
        self._busy_until = 0.0
        self.connected = True
        self.last_error = None
        log.info("%s: opened %s as Open DMX (%d baud, 8N2, break by %s)", self.name, path, DMX_BAUD, self.break_method)

    def write(self, frame: object) -> None:
        assert self.port is not None and isinstance(frame, (bytes, bytearray))
        port = self.port
        wait = self._busy_until - time.monotonic()
        if wait > 0:
            time.sleep(wait)  # the previous frame is still on its way out
        # tcdrain (flush) is what made the writes go through on macOS (probe, 2026-10-11): the
        # driver seems to send nothing until it is asked to drain
        port.flush()
        if self.break_method == "baud":
            port.baudrate = DMX_BREAK_BAUD
            time.sleep(self.SETTLE_S)
            port.write(b"\x00")
            port.flush()
            time.sleep(self.SETTLE_S)  # the break byte must be out before the rate changes back
            port.baudrate = DMX_BAUD
            time.sleep(self.SETTLE_S)
        else:
            port.break_condition = True
            time.sleep(self.BREAK_S)
            port.break_condition = False
            time.sleep(self.MARK_S)
        data = b"\x00" + bytes(frame[:512])
        port.write(data)
        self._busy_until = time.monotonic() + len(data) * DMX_BYTE_S + 0.002
