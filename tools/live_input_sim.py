"""Simulates live DMX input for testing routes (items 57 to 59) without a console.

    py tools/live_input_sim.py artnet --universes 0,1 --pattern sweep
    py tools/live_input_sim.py artnet --universes 3 --pattern const --value 200 --seconds 5

Sends ArtDMX packets (30 per second by default) to this computer's Art-Net input (127.0.0.1, port 6454).
Patterns: ``sweep`` (a sine wave that runs along the channels), ``ramp`` (channel n = n), ``const`` (``--value``),
``blink`` (all channels 0 and 255 once a second). Stops after ``--seconds`` (0 = until Ctrl+C).
"""

from __future__ import annotations

import argparse
import math
import socket
import struct
import time


def artdmx(universe: int, data: bytes, sequence: int) -> bytes:
    return (
        b"Art-Net\x00" + struct.pack("<H", 0x5000) + struct.pack(">H", 14) + bytes([sequence & 0xFF, 0])
        + bytes([universe & 0xFF, (universe >> 8) & 0x7F]) + struct.pack(">H", len(data)) + data
    )


def frame(pattern: str, universe: int, t: float, value: int, count: int) -> bytes:
    if pattern == "ramp":
        return bytes(i % 256 for i in range(count))
    if pattern == "const":
        return bytes([value]) * count
    if pattern == "blink":
        return bytes([255 if int(t) % 2 == 0 else 0]) * count
    return bytes(int((math.sin(t * 2 + i / 8 + universe) + 1) / 2 * 255) for i in range(count))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kind", choices=["artnet"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=6454)
    p.add_argument("--universes", default="0", help="Art-Net universes (port addresses), comma separated")
    p.add_argument("--pattern", choices=["sweep", "ramp", "const", "blink"], default="sweep")
    p.add_argument("--value", type=int, default=128, help="the value of the const pattern")
    p.add_argument("--channels", type=int, default=512)
    p.add_argument("--rate", type=float, default=30.0, help="packets per second and universe")
    p.add_argument("--seconds", type=float, default=0.0)
    a = p.parse_args()
    universes = [int(x) for x in a.universes.split(",") if x.strip()]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    start, seq = time.monotonic(), 0
    try:
        while a.seconds <= 0 or time.monotonic() - start < a.seconds:
            t = time.monotonic() - start
            seq = seq % 255 + 1
            for u in universes:
                sock.sendto(artdmx(u, frame(a.pattern, u, t, a.value, a.channels), seq), (a.host, a.port))
            time.sleep(1.0 / a.rate)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
