#!/usr/bin/env python3
"""Find out how an Enttec Open DMX USB (bare FTDI chip) has to be driven on this computer.

Close PitchControl first (the port must be free), connect the interface and a fixture, then:

    backend/.venv/bin/python tools/open_dmx_probe.py [--port /dev/cu.usbserial-XXXX]
                                                      [--channels 1-8] [--value 255]

It tries a series of ways of writing to the port, each for 3 seconds, tells you which step fails
(and the state of the port when it does), and asks whether the fixture reacted. Set the fixture to
the DMX address in --channels first (a dimmer or colour fixture on channel 1 is the easiest).
Variants S1 and S2 are only about whether the port accepts a 513 byte write at all; the fixture
cannot react to them (no break), just press Enter.
At the end it prints which variants worked; send that to the developer.
"""
import argparse
import sys
import time

import serial
from serial.tools import list_ports

BAUD, BREAK_BAUD = 250000, 90000
BYTE_S = 11 / BAUD


class Variant:
    def __init__(self, name, why="", *, mode="baud", settle=0.0, flush_before=False, flush_after_break=False,
                 flush_after_frame=False, poll_outq=False, chunk=0, open_baud=BAUD, open_stop=2, open_bits=8,
                 rts=None, dtr=None, ask=True, clear_flow=False):
        self.name, self.why, self.mode, self.settle = name, why, mode, settle
        self.flush_before, self.flush_after_break, self.flush_after_frame = flush_before, flush_after_break, flush_after_frame
        self.poll_outq, self.chunk, self.open_baud, self.open_stop, self.open_bits = poll_outq, chunk, open_baud, open_stop, open_bits
        self.rts, self.dtr, self.ask, self.clear_flow = rts, dtr, ask, clear_flow


VARIANTS = [
    # the flow-control flags of the tty switched off (the suspected reason for output never leaving)
    Variant("T1 flow flags cleared, plain write 115200 8N1", "basic transmit sanity", mode="plain", open_baud=115200, open_stop=1, flush_after_frame=True, ask=False, clear_flow=True),
    Variant("T2 flow flags cleared, plain write 250000 8N2", "", mode="plain", flush_after_frame=True, ask=False, clear_flow=True),
    Variant("T3 flow flags cleared, baud trick with flush and 2 ms waits", "the app's sequence", flush_before=True, flush_after_break=True, settle=0.002, clear_flow=True),
    # does the port accept a 513 byte write at all?
    Variant("S1 plain write, 115200 8N1, no break", "basic transmit sanity", mode="plain", open_baud=115200, open_stop=1, flush_after_frame=True, ask=False),
    Variant("S2 plain write, 250000 8N2, no break", "does the DMX line format work?", mode="plain", flush_after_frame=True, ask=False),
    Variant("S3 plain write, 250000 8N2, no flush", "as S2 without tcdrain", mode="plain", ask=False),
    # the sequence of the first app version that did not time out: tcdrain between the steps
    Variant("J baud trick with flush (tcdrain) between steps", "the first version of the app", flush_before=True, flush_after_break=True),
    Variant("K J plus 2 ms waits", "", flush_before=True, flush_after_break=True, settle=0.002),
    Variant("L J, flush also after the frame", "", flush_before=True, flush_after_break=True, flush_after_frame=True),
    Variant("M waits until the output queue is empty instead of tcdrain", "TIOCOUTQ polling", poll_outq=True, settle=0.002),
    Variant("N J, frame in chunks of 64 bytes", "", flush_before=True, flush_after_break=True, chunk=64),
    Variant("O J, opened at 115200 8N1 then switched", "the custom rate set after opening", flush_before=True, flush_after_break=True, open_baud=115200, open_stop=1),
    Variant("P J with RTS and DTR low", "", flush_before=True, flush_after_break=True, rts=False, dtr=False),
    Variant("Q break line with flush", "TIOCSBRK", mode="break", flush_before=True, flush_after_break=True, settle=0.005),
]


FLOW_NAMES = ("CRTSCTS", "CCTS_OFLOW", "CRTS_IFLOW", "CDTR_IFLOW", "CDSR_OFLOW", "CCAR_OFLOW", "MDMBUF")


def flow_flags(port, clear=False):
    """The hardware flow-control flags set on the tty (macOS: the driver may hold output until a
    modem line is up); with clear=True they are switched off. Returns their names."""
    try:
        import termios
    except ImportError:
        return "n/a"
    attrs = termios.tcgetattr(port.fd)
    was = [n for n in FLOW_NAMES if getattr(termios, n, 0) and attrs[2] & getattr(termios, n)]
    if clear:
        mask = 0
        for n in FLOW_NAMES:
            mask |= getattr(termios, n, 0)
        attrs[2] &= ~mask
        termios.tcsetattr(port.fd, termios.TCSANOW, attrs)
    return " ".join(was) or "none"


def frame_for(channels, value):
    data = bytearray(512)
    for ch in channels:
        data[ch - 1] = value
    return bytes(data)


def drain(port, poll):
    if poll:
        t0 = time.monotonic()
        while port.out_waiting and time.monotonic() - t0 < 1.0:
            time.sleep(0.0005)
    else:
        port.flush()


def state(port):
    out = []
    for name in ("out_waiting", "cts", "dsr", "cd", "ri"):
        try:
            out.append(f"{name}={getattr(port, name)}")
        except Exception as exc:  # noqa: BLE001
            out.append(f"{name}=?({type(exc).__name__})")
    return " ".join(out)


def run(port_path, v, frame, seconds):
    t0 = time.monotonic()
    try:
        port = serial.Serial(port_path, v.open_baud, bytesize=v.open_bits, parity="N", stopbits=v.open_stop, timeout=0, write_timeout=1)
    except Exception as exc:  # noqa: BLE001
        return False, f"open failed: {exc!r}"
    step = "setup"
    flags = "?"
    try:
        flags = flow_flags(port, clear=v.clear_flow)
        if v.rts is not None:
            port.rts = v.rts
        if v.dtr is not None:
            port.dtr = v.dtr
        if v.open_baud != BAUD or v.open_stop != 2:
            step = "switch to 250000 8N2"
            port.stopbits = 2
            port.baudrate = BAUD
        time.sleep(0.02)
        frames = 0
        data = b"\x00" + frame
        while time.monotonic() - t0 < seconds:
            if v.mode == "baud":
                if v.flush_before:
                    step = "drain before the break"
                    drain(port, v.poll_outq)
                step = "set 90000 baud"
                port.baudrate = BREAK_BAUD
                time.sleep(v.settle)
                step = "write break byte"
                port.write(b"\x00")
                if v.flush_after_break or v.poll_outq:
                    step = "drain after the break byte"
                    drain(port, v.poll_outq)
                time.sleep(v.settle)
                step = "set 250000 baud"
                port.baudrate = BAUD
                time.sleep(v.settle)
            elif v.mode == "break":
                if v.flush_before:
                    step = "drain before the break"
                    drain(port, v.poll_outq)
                step = "break on"
                port.break_condition = True
                time.sleep(v.settle)
                step = "break off"
                port.break_condition = False
                time.sleep(v.settle)
            step = "write frame"
            if v.chunk:
                for i in range(0, len(data), v.chunk):
                    port.write(data[i:i + v.chunk])
            else:
                port.write(data)
            if v.flush_after_frame:
                step = "drain after the frame"
                drain(port, v.poll_outq)
            elif v.mode == "plain":
                time.sleep(len(data) * BYTE_S + 0.002)
            else:
                time.sleep(len(data) * BYTE_S + 0.002)
            frames += 1
        return True, f"{frames} frames ({frames / seconds:.0f} per second); flow flags {'cleared: ' if v.clear_flow else ''}{flags}"
    except Exception as exc:  # noqa: BLE001
        try:
            extra = state(port)
        except Exception:  # noqa: BLE001
            extra = "?"
        return False, f"failed at '{step}': {exc!r}; port state: {extra}; flow flags at open: {flags}"
    finally:
        try:
            port.close()
        except Exception:  # noqa: BLE001
            pass


def parse_channels(text):
    out = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [c for c in out if 1 <= c <= 512]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--channels", default="1-8", help="channels to set, e.g. 1-8 or 1,2,5")
    ap.add_argument("--value", type=int, default=255)
    ap.add_argument("--seconds", type=float, default=3.0)
    args = ap.parse_args()

    port_path = args.port
    if not port_path:
        ports = [p for p in list_ports.comports() if p.vid is not None]
        for i, p in enumerate(ports):
            print(f"  [{i + 1}] {p.device}  {p.description}  {p.serial_number or ''}")
        if not ports:
            sys.exit("no USB serial ports found")
        port_path = ports[int(input("port number: ")) - 1].device
    frame = frame_for(parse_channels(args.channels), args.value)
    print(f"\nport {port_path}, channels {args.channels} = {args.value}; {len(VARIANTS)} variants of {args.seconds:.0f} s each\n")

    results = []
    for v in VARIANTS:
        print(f"--- {v.name}" + (f"   ({v.why})" if v.why else ""))
        ok, detail = run(port_path, v, frame, args.seconds)
        print(f"    port: {'OK' if ok else 'FAILED'}: {detail}")
        reacted = None
        if ok and v.ask:
            answer = input("    did the fixture react? [y/n/q] ").strip().lower()
            if answer == "q":
                break
            reacted = answer == "y"
        results.append((v.name, ok, reacted, detail))
        time.sleep(0.5)

    print("\n=== summary (send this) ===")
    for name, ok, reacted, detail in results:
        print(f"{name}: port {'ok' if ok else 'FAILED'}, fixture {'-' if reacted is None else ('reacted' if reacted else 'did not react')}; {detail}")


if __name__ == "__main__":
    main()
