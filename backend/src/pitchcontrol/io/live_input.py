"""Live DMX input: Art-Net and an Enttec DMX USB Pro that receives (item 57), the sources of the routes (item 58).

Each source keeps the **latest 512 values** of what it receives, plus the time of the last packet and the sender.
The receiver threads only write into the store, under a small lock; the engine reads the values at frame time and
never waits for a socket or a serial port. Nothing here forgets: when a sender goes quiet the values stay (a route
holds the last value, Miro 2026-10-22), only the "last seen" age grows.

Source keys: ``artnet:<port address>`` (the raw 15-bit wire value: net, sub-net, universe) and ``dmx`` (the Pro).
"""

from __future__ import annotations

import errno
import ipaddress
import logging
import socket
import struct
import sys
import threading
import time
from collections.abc import Callable
from typing import NamedTuple

import serial

from ..config.models import ArtNetInputSettings, DeviceRef, DmxInputSettings, LiveInputSettings, OutputSettings
from .devices import resolve_port

log = logging.getLogger(__name__)

DMX_KEY = "dmx"
RETRY_S = 3.0  # a port that couldn't be opened (taken, device missing) is tried again this often
RATE_WINDOW_S = 1.0  # packets per second are counted over at least this long
LOOPBACK = "127.0.0.1"

PRO_LABEL_RECEIVED = 5  # Enttec DMX USB Pro API: "Received DMX Packet", unsolicited while the port is an input
PRO_LABEL_RECEIVE_MODE = 8  # "Receive DMX on Change": 0 = send always, 1 = only on change
PRO_LABEL_CHANGE_OF_STATE = 9  # "Received DMX Change Of State Packet"


def artnet_key(port_address: int) -> str:
    return f"artnet:{port_address}"


# ---------------------------------------------------------------------------- Art-Net


class ArtDmx(NamedTuple):
    port_address: int  # 15 bits: net (7) · sub-net (4) · universe (4), as on the wire
    sequence: int  # 0 = the sender doesn't number its packets
    physical: int
    data: bytes  # 1 to 512 channels


def parse_artdmx(packet: bytes) -> ArtDmx | None:
    """An ArtDMX (OpDmx 0x5000) packet, or None for anything else (ArtPoll, a short or damaged packet)."""
    if len(packet) < 19 or packet[:8] != b"Art-Net\x00":
        return None
    if struct.unpack_from("<H", packet, 8)[0] != 0x5000:
        return None
    if struct.unpack_from(">H", packet, 10)[0] < 14:  # protocol version
        return None
    sequence, physical, sub_uni, net = packet[12], packet[13], packet[14], packet[15]
    length = struct.unpack_from(">H", packet, 16)[0]
    if not 1 <= length <= 512:
        return None
    data = packet[18 : 18 + length]  # a packet cut short gives what is there
    if not data:
        return None
    return ArtDmx(((net & 0x7F) << 8) | sub_uni, sequence, physical, bytes(data))


def adapter_choices() -> list[tuple[str, str]]:
    """``(name, IPv4 address)`` of this computer's network adapters, loopback too (a test script on this computer
    sends there)."""
    from ..server.network import adapter_addresses

    return [*adapter_addresses(), ("Loopback", LOOPBACK)]


def _adapter_network(ip: str) -> ipaddress.IPv4Network | None:
    try:
        import ifaddr

        for adapter in ifaddr.get_adapters():
            for a in adapter.ips:
                if a.is_IPv4 and a.ip == ip:
                    return ipaddress.IPv4Network(f"{ip}/{a.network_prefix}", strict=False)
    except Exception:  # noqa: BLE001
        pass
    return None


def local_addresses() -> set[str]:
    return {ip for _, ip in adapter_choices()} | {LOOPBACK}


# ---------------------------------------------------------------------------- the store


class _Source:
    def __init__(self) -> None:
        self.values = bytearray(512)
        self.sender = ""
        self.last = 0.0  # clock() of the last packet
        self.packets = 0
        self.sequence = 0
        self.rate_t = 0.0  # the packets-per-second window: when it started and the count then
        self.rate_n = 0
        self.rate = 0.0


class InputStore:
    """The latest values of every source that has sent anything, and what the Inputs page shows of them."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._sources: dict[str, _Source] = {}

    def put(self, key: str, data: bytes, sender: str = "", sequence: int = 0) -> None:
        """Take a packet. Channels the packet doesn't carry keep their last value."""
        now = self._clock()
        with self._lock:
            src = self._sources.get(key)
            if src is None:
                src = self._sources[key] = _Source()
                src.rate_t = now
            src.values[: len(data)] = data[:512]
            src.sender = sender
            src.last = now
            src.packets += 1
            src.sequence = sequence

    def get(self, key: str) -> bytes | None:
        """The latest 512 values, or None while the source has never sent."""
        with self._lock:
            src = self._sources.get(key)
            return bytes(src.values) if src is not None else None

    def clear(self, prefix: str = "") -> None:
        with self._lock:
            for k in [k for k in self._sources if k.startswith(prefix)]:
                del self._sources[k]

    def snapshot(self, prefix: str = "") -> list[dict]:
        """One entry per source with the prefix, in key order: its key, sender, packets per second, seconds since the
        last packet and the packet count."""
        now = self._clock()
        out = []
        with self._lock:
            for key in sorted(self._sources, key=lambda k: (len(k), k)):
                if not key.startswith(prefix):
                    continue
                src = self._sources[key]
                if now - src.rate_t >= RATE_WINDOW_S:
                    src.rate = (src.packets - src.rate_n) / (now - src.rate_t)
                    src.rate_t, src.rate_n = now, src.packets
                age = now - src.last
                if age > 2 * RATE_WINDOW_S + 1:
                    src.rate = 0.0
                out.append({"key": key, "sender": src.sender, "pps": round(src.rate, 1), "age": round(age, 2), "packets": src.packets})
        return out


# ---------------------------------------------------------------------------- Art-Net receiver


class ArtNetReceiver:
    """The UDP listener. ``own_ports()``: the source ports of this app's own Art-Net output; a packet that comes from
    one of this computer's addresses on such a port is the app's own and is dropped, so an output universe can't
    feed back into a route."""

    def __init__(self, store: InputStore, cfg: ArtNetInputSettings, own_ports: Callable[[], set[int]] = lambda: set()) -> None:
        self.store = store
        self.cfg = cfg
        self.own_ports = own_ports
        self.sock: socket.socket | None = None
        self.listening = False
        self.error: str | None = None
        self.packets = 0
        self.own = 0  # packets dropped as the app's own
        self.other = 0  # received, but not ArtDMX
        self._net: ipaddress.IPv4Network | None = None
        self._local: set[str] = set()
        self._local_at = -1e9
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="artnet-in", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        self._close()

    def _close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock, self.listening = None, False

    def _open(self) -> None:
        cfg = self.cfg
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # another Art-Net program may listen too
            if hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            host = cfg.adapter
            if host and sys.platform != "win32":
                # elsewhere a socket bound to one address doesn't get the broadcasts: listen on all, keep the adapter's network
                self._net = _adapter_network(host)
                host = ""
            else:
                self._net = None
            sock.bind((host, cfg.port))
        except OSError:
            sock.close()
            raise
        sock.settimeout(0.5)
        self.sock = sock
        self.listening, self.error = True, None
        log.info("Art-Net input: listening on %s:%d", cfg.adapter or "all adapters", cfg.port)

    def _is_own(self, addr: tuple[str, int]) -> bool:
        if addr[1] not in self.own_ports():
            return False
        now = time.monotonic()
        if now - self._local_at > 5.0:  # the adapters change when the wifi does
            self._local, self._local_at = local_addresses(), now
        return addr[0] in self._local

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.sock is None:
                try:
                    self._open()
                except OSError as exc:
                    message = _port_message(self.cfg.port, exc)
                    if message != self.error:
                        log.warning("Art-Net input: %s", message)
                    self.error = message
                    self._stop.wait(RETRY_S)
                    continue
            try:
                packet, addr = self.sock.recvfrom(2048)  # type: ignore[union-attr]
            except socket.timeout:
                continue
            except OSError as exc:
                if self._stop.is_set():
                    break
                if exc.errno in (errno.ECONNRESET, 10054):  # Windows: an ICMP "port unreachable" from an earlier send
                    continue
                self.error = f"Art-Net input stopped: {exc.strerror or exc}"
                log.warning("%s", self.error)
                self._close()
                continue
            self.handle(packet, addr)

    def handle(self, packet: bytes, addr: tuple[str, int]) -> None:
        """One datagram (called by the thread; the tests call it directly)."""
        if self._net is not None and ipaddress.IPv4Address(addr[0]) not in self._net:
            return
        art = parse_artdmx(packet)
        if art is None:
            self.other += 1
            return
        if self._is_own(addr):
            self.own += 1
            return
        self.packets += 1
        self.store.put(artnet_key(art.port_address), art.data, addr[0], art.sequence)

    def status(self) -> dict:
        return {
            "enabled": True,
            "listening": self.listening,
            "error": self.error,
            "port": self.cfg.port,
            "adapter": self.cfg.adapter,
            "packets": self.packets,
            "own_ignored": self.own,
            "universes": [{**u, "universe": int(u["key"].split(":", 1)[1])} for u in self.store.snapshot("artnet:")],
        }


def _port_message(port: int, exc: OSError) -> str:
    if exc.errno in (errno.EADDRINUSE, errno.EACCES, 10048, 10013):
        return f"Port {port} can't be used for Art-Net input (another program has it without sharing): choose another port"
    if exc.errno in (errno.EADDRNOTAVAIL, 10049):
        return "The chosen network adapter has no such address now: choose another one, or 'All adapters'"
    return f"Can't listen on port {port}: {exc.strerror or exc}"


# ---------------------------------------------------------------------------- Enttec DMX USB Pro


def pro_message(label: int, data: bytes = b"") -> bytes:
    n = len(data)
    return bytes([0x7E, label, n & 0xFF, (n >> 8) & 0xFF]) + data + b"\xe7"


class ProParser:
    """Splits the Pro's byte stream into ``(label, data)`` messages: 0x7E, label, length (2 bytes, LSB first), data,
    0xE7. Bytes that don't make a message are skipped one by one, so a stream that starts in the middle recovers."""

    MAX_LENGTH = 600

    def __init__(self) -> None:
        self.buf = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[int, bytes]]:
        self.buf += chunk
        out: list[tuple[int, bytes]] = []
        buf = self.buf
        while buf:
            if buf[0] != 0x7E:
                at = buf.find(0x7E)
                del buf[: at if at >= 0 else len(buf)]
                continue
            if len(buf) < 4:
                break
            length = buf[2] | (buf[3] << 8)
            if length > self.MAX_LENGTH:
                del buf[0]
                continue
            if len(buf) < 5 + length:
                break
            if buf[4 + length] != 0xE7:
                del buf[0]
                continue
            out.append((buf[1], bytes(buf[4 : 4 + length])))
            del buf[: 5 + length]
        return out


class ProDecoder:
    """What the Pro's received-DMX messages say: the 512 channels after each message."""

    def __init__(self) -> None:
        self.array = bytearray(513)  # start code + 512 channels, as in Enttec's change-of-state algorithm
        self.errors = 0  # messages with an error status, or another start code than 0

    def decode(self, label: int, data: bytes) -> bytes | None:
        """The 512 channels now, or None when the message carries none (another label, a damaged packet)."""
        if label == PRO_LABEL_RECEIVED:
            if len(data) < 2 or data[0] != 0 or data[1] != 0:  # status 0 = valid; start code 0 = DMX (not RDM or text)
                self.errors += 1
                return None
            channels = data[2:514]
            self.array[1 : 1 + len(channels)] = channels
            return bytes(self.array[1:513])
        if label == PRO_LABEL_CHANGE_OF_STATE and len(data) >= 6:
            start, bits, values = data[0], data[1:6], data[6:]
            i = 0
            for n in range(40):
                if bits[n // 8] >> (n % 8) & 1:
                    at = start * 8 + n
                    if i < len(values) and at < 513:
                        self.array[at] = values[i]
                    i += 1
            return bytes(self.array[1:513])
        return None


class DmxProReceiver:
    """An Enttec DMX USB Pro whose DMX port is an input. Enttec's API: the port is an input unless "Output Only Send
    DMX" was sent, and any other request turns it into one; the one request made here, "Receive DMX on Change" with
    0 = send always, says what the widget sends."""

    def __init__(self, store: InputStore, ref: DeviceRef) -> None:
        self.store = store
        self.ref = ref
        self.port: serial.Serial | None = None
        self.connected = False
        self.error: str | None = None
        self.port_name: str | None = None
        self.decoder = ProDecoder()
        self.parser = ProParser()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="dmx-in", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        self._close()

    def _close(self) -> None:
        if self.port is not None:
            try:
                self.port.close()
            except Exception:  # noqa: BLE001
                pass
        self.port, self.connected = None, False

    def _open(self) -> None:
        path = resolve_port(self.ref)
        if not path:
            raise ConnectionError("device not found (check the Inputs page)")
        self.port = serial.Serial(path, 57600, timeout=0.1, write_timeout=1)
        self.port.write(pro_message(PRO_LABEL_RECEIVE_MODE, b"\x00"))
        self.port.reset_input_buffer()
        self.parser, self.decoder = ProParser(), ProDecoder()
        self.connected, self.error, self.port_name = True, None, path
        log.info("DMX input: opened %s as an Enttec DMX USB Pro (receiving)", path)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self.port is None:
                    self._open()
                self.feed(self.port.read(1024) or b"")  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001 - a missing or pulled device must never kill the thread
                message = str(exc) or exc.__class__.__name__
                if message != self.error:
                    log.warning("DMX input: %s", message)
                self.error = message
                self._close()
                self._stop.wait(RETRY_S)

    def feed(self, chunk: bytes) -> None:
        """Bytes from the port (the thread's, and the tests')."""
        for label, data in self.parser.feed(chunk):
            values = self.decoder.decode(label, data)
            if values is not None:
                self.store.put(DMX_KEY, values, self.port_name or "")

    def status(self) -> dict:
        entry = next(iter(self.store.snapshot(DMX_KEY)), None)
        return {
            "enabled": True,
            "connected": self.connected,
            "error": self.error,
            "port": self.port_name,
            "damaged": self.decoder.errors,
            "pps": entry["pps"] if entry else 0.0,
            "age": entry["age"] if entry else None,
            "packets": entry["packets"] if entry else 0,
        }


def _device_key(ref: DeviceRef) -> str | None:
    return ref.serial_number or ref.port


# ---------------------------------------------------------------------------- the manager


class LiveInput:
    """Both inputs of one app. ``apply`` makes the receivers match the settings (only a changed one is restarted: the
    DMX input and the Art-Net listener don't touch each other)."""

    def __init__(self, own_ports: Callable[[], set[int]] = lambda: set(), clock: Callable[[], float] = time.monotonic) -> None:
        self.store = InputStore(clock)
        self.own_ports = own_ports
        self.artnet: ArtNetReceiver | None = None
        self.dmx: DmxProReceiver | None = None
        self._dmx_error: str | None = None  # why the DMX input wasn't started
        self._cfg = LiveInputSettings()

    def apply(self, cfg: LiveInputSettings, outputs: OutputSettings) -> None:
        old = self._cfg
        self._cfg = cfg
        if self.artnet is not None and (not cfg.artnet.enabled or cfg.artnet != old.artnet):
            self.artnet.stop()
            self.artnet = None
        if cfg.artnet.enabled and self.artnet is None:
            self.artnet = ArtNetReceiver(self.store, cfg.artnet, self.own_ports)
            self.artnet.start()

        clash = self._output_clash(cfg.dmx, outputs) if cfg.dmx.enabled else None
        self._dmx_error = clash
        if self.dmx is not None and (not cfg.dmx.enabled or cfg.dmx != old.dmx or clash):
            self.dmx.stop()
            self.dmx = None
        if clash:
            log.warning("DMX input: %s, not started", clash)
        elif cfg.dmx.enabled and self.dmx is None:
            self.dmx = DmxProReceiver(self.store, cfg.dmx.device)
            self.dmx.start()

    @staticmethod
    def _output_clash(dmx: DmxInputSettings, outputs: OutputSettings) -> str | None:
        """A Pro that receives can't send: the same device as an enabled USB DMX output is refused (the output wins)."""
        key = _device_key(dmx.device)
        if not key:
            return None
        for i, e in enumerate(outputs.enttec):
            if e.enabled and _device_key(e.device) == key:
                return f"same device as output interface {i + 1}: a Pro that receives can't send, so turn that output off first"
        return None

    def stop(self) -> None:
        if self.artnet is not None:
            self.artnet.stop()
        if self.dmx is not None:
            self.dmx.stop()
        self.artnet = self.dmx = None

    def latest(self, key: str) -> bytes | None:
        """The latest 512 values of a source, None while it has never sent. Kept when the receiver is switched off."""
        return self.store.get(key)

    def sources(self) -> dict[str, dict]:
        """Every source that has sent something, by key: sender, packets per second, seconds since the last packet."""
        return {e["key"]: e for e in self.store.snapshot()}

    def sources(self) -> dict[str, dict]:
        """Every source that has sent something, by key: sender, packets per second, seconds since the last packet."""
        return {e["key"]: e for e in self.store.snapshot()}

    def status(self) -> dict:
        art = self.artnet.status() if self.artnet is not None else {"enabled": False}
        if self.dmx is not None:
            dmx = self.dmx.status()
        elif self._dmx_error:
            dmx = {"enabled": True, "connected": False, "error": self._dmx_error}
        else:
            dmx = {"enabled": False}
        return {"artnet": art, "dmx": dmx}
