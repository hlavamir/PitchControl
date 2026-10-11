#!/usr/bin/env python3
"""Find out how an Enttec Open DMX USB (bare FTDI chip) has to be driven on this computer.

Close PitchControl first (the port must be free), connect the interface and a fixture, then:

    backend/.venv/bin/python tools/open_dmx_probe.py [--port /dev/cu.usbserial-XXXX]
                                                      [--channels 1-8] [--value 255]

It tries a series of ways of setting up the port and making the DMX break, each for 3 seconds of
frames, tells you where a write fails, and asks whether the fixture reacted. Set the fixture to
the DMX address in --channels first (a dimmer or colour fixture on channel 1 is the easiest).
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
    def __init__(self, name, why, rts=None, dtr=None, flush_out=False, method="baud", settle=0.002, close_first=False, stopbits=2):
        self.name, self.why, self.rts, self.dtr, self.flush_out = name, why, rts, dtr, flush_out
        self.method, self.settle, self.close_first, self.stopbits = method, settle, close_first, stopbits


VARIANTS = [
    Variant("A baud trick, port left as the system opens it", "no RTS / DTR change, 2 ms between steps"),
    Variant("B baud trick, RTS and DTR low", "as the app did in its last test (it timed out there)", rts=False, dtr=False),
    Variant("C baud trick, RTS low only", "the RS-485 driver of some dongles follows RTS", rts=False),
    Variant("D baud trick, DTR low only", "", dtr=False),
    Variant("E baud trick, RTS and DTR high", "explicit, the macOS default", rts=True, dtr=True),
    Variant("F baud trick, output buffer flushed after opening", "", flush_out=True),
    Variant("G baud trick, slow steps (10 ms)", "in case the driver needs longer for a rate change", settle=0.010),
    Variant("H break line, long break (5 ms)", "TIOCSBRK; failed with write timeouts on macOS before", method="break", settle=0.005),
    Variant("I baud trick, 1 stop bit", "in case the driver mishandles two stop bits", stopbits=1),
]


def frame_for(channels, value):
    data = bytearray(512)
    for ch in channels:
        data[ch - 1] = value
    return bytes(data)


def run(port_path, v, frame, seconds):
    t0 = time.monotonic()
    try:
        port = serial.Serial(port_path, BAUD, bytesize=8, parity="N", stopbits=v.stopbits, timeout=0, write_timeout=1)
    except Exception as exc:  # noqa: BLE001
        return False, f"open failed: {exc!r}"
    step = "setup"
    try:
        if v.rts is not None:
            port.rts = v.rts
        if v.dtr is not None:
            port.dtr = v.dtr
        if v.flush_out:
            port.reset_output_buffer()
        time.sleep(0.02)
        frames, busy_until = 0, 0.0
        while time.monotonic() - t0 < seconds:
            wait = busy_until - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            if v.method == "baud":
                step = "set 90000 baud"
                port.baudrate = BREAK_BAUD
                time.sleep(v.settle)
                step = "write break byte"
                port.write(b"\x00")
                time.sleep(v.settle)
                step = "set 250000 baud"
                port.baudrate = BAUD
                time.sleep(v.settle)
            else:
                step = "break on"
                port.break_condition = True
                time.sleep(v.settle)
                step = "break off"
                port.break_condition = False
                time.sleep(v.settle)
            step = "write frame"
            data = b"\x00" + frame
            port.write(data)
            busy_until = time.monotonic() + len(data) * BYTE_S + 0.002
            frames += 1
        return True, f"{frames} frames ({frames / seconds:.0f} per second)"
    except Exception as exc:  # noqa: BLE001
        return False, f"failed at '{step}': {exc!r}"
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
        if ok:
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
