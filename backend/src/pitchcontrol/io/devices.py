"""USB serial device discovery and matching (by serial number / VID:PID, port path as fallback)."""

from __future__ import annotations

import logging

from serial.tools import list_ports

from ..config.models import DeviceRef

log = logging.getLogger(__name__)


# What an FTDI-based DMX interface calls itself. Both the Enttec DMX USB Pro (FT245R) and the Open DMX
# USB / bare RS-485 dongles (FT232R) have the same VID:PID 0403:6001, the product string tells them apart.
_PRO_WORDS = ("dmx usb pro", "ultradmx", "dmxking", "ft245r", "usb fifo", "enttec")
_OPEN_WORDS = ("ft232r", "ft232", "usb uart", "open dmx", "rs485", "rs-485", "485")


def guess_dmx_type(*texts: str | None) -> str | None:
    """"pro" (the interface makes the DMX signal from our packets), "open" (a bare FTDI chip: we make
    the signal) or None (unknown) from the USB description / product / manufacturer strings."""
    text = " ".join(t for t in texts if t).lower()
    if not text:
        return None
    if any(w in text for w in _PRO_WORDS):
        return "pro"
    if any(w in text for w in _OPEN_WORDS):
        return "open"
    return None


def device_info(ref: DeviceRef) -> dict | None:
    """The currently connected device of a configured reference (serial number, VID:PID or port)."""
    for d in list_serial_devices():
        if ref.serial_number and d["serial_number"] == ref.serial_number:
            return d
    for d in list_serial_devices():
        if ref.port and d["port"] == ref.port:
            return d
    return None


def detect_dmx_type(ref: DeviceRef) -> str:
    """The type of a configured USB DMX interface: from the connected device, else from what was
    stored when it was chosen; the Enttec Pro protocol when nothing tells."""
    info = device_info(ref)
    if info is not None and info.get("dmx_type"):
        return info["dmx_type"]
    return guess_dmx_type(ref.description) or "pro"


def list_serial_devices() -> list[dict]:
    devices = []
    # USB devices first; built-in ports (Bluetooth, debug consoles) have no VID and are listed last
    for p in sorted(list_ports.comports(), key=lambda p: (p.vid is None, p.device)):
        description = p.product or (p.description if p.description and p.description != "n/a" else None)
        label = description or p.device.rsplit("/", 1)[-1]
        if p.serial_number:
            label += f" — {p.serial_number}"
        label += f" ({p.device})"
        devices.append(
            {
                "port": p.device,
                "description": description,
                "manufacturer": p.manufacturer,
                "serial_number": p.serial_number,
                "vid": p.vid,
                "pid": p.pid,
                "label": label,
                "dmx_type": guess_dmx_type(p.product, p.description if p.description != "n/a" else None, p.manufacturer),
            }
        )
    return devices


def resolve_port(ref: DeviceRef) -> str | None:
    """Find the current port path of a configured device."""
    if ref is None:
        return None
    ports = list(list_ports.comports())
    if ref.serial_number:
        for p in ports:
            if p.serial_number == ref.serial_number and (ref.vid is None or p.vid == ref.vid):
                return p.device
    if ref.vid is not None and ref.pid is not None and not ref.serial_number:
        matches = [p for p in ports if p.vid == ref.vid and p.pid == ref.pid]
        if len(matches) == 1:
            return matches[0].device
    if ref.port:
        return ref.port
    return None
