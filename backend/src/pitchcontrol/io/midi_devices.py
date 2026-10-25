"""The MIDI devices of this computer (item 89): the one owner of every MIDI input port.

A MIDI input can be opened once only, by one program (Windows, WinMM), so one object opens them all and hands every
message on, with the device it came from, to the subscribers: the mapping and the monitor (``MidiInput``), the routes
of the Control Desk (``MidiRouteHub``). Nothing else opens a port.

The list of devices is per computer (``midi_devices`` in machine.json, keyed by ``port_key``): a device seen for the
first time is added with In on, saved, and opened; switching In off closes the port at once, so another program can
take it; a device that is unplugged is closed and opened again when it comes back (item 33, now per device). ``sync``
does it all, one look at a time: the watchdog calls it every couple of seconds, and a change from the page calls it
at once.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..config.models import MidiDeviceSetting
from .midi_in import _winmm_indices, list_midi_inputs_checked, match_port, mido, port_key

log = logging.getLogger(__name__)

Subscriber = Callable[[str, str, Any], None]  # (device key, device name, mido message)


@dataclass
class _Runtime:
    """What this run knows of a device (in memory only)."""

    port: Any = None
    state: str | None = None  # "connected" | "off" | "missing" | "error"; None before the first look
    error: str | None = None
    lost: float | None = None  # when the open port was pulled (wall clock), None: not found at the start
    back: float | None = None  # when it opened again by itself
    received: int = 0
    last: float | None = None  # time.monotonic() of its last message


def wait_between_looks(stop: threading.Event, seconds: float) -> bool:
    """The watchdog's pause between two looks; True when ``stop`` is set. On macOS CoreMIDI tells a process about
    devices plugged in after its start only through the run loop of the thread that lists them: a worker thread that
    just sleeps keeps seeing the devices of the start, so a controller plugged in later never showed up (item 92). The
    watchdog runs its run loop while it waits instead (a plain wait elsewhere)."""
    if sys.platform != "darwin":
        return stop.wait(seconds)
    try:
        from CoreFoundation import CFRunLoopRunInMode, kCFRunLoopDefaultMode
    except ImportError:  # pragma: no cover - pywebview brings PyObjC on macOS
        return stop.wait(seconds)
    end = time.monotonic() + seconds
    while not stop.is_set() and time.monotonic() < end:
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, min(0.2, max(0.0, end - time.monotonic())), False)
    return stop.is_set()


def open_error_text(exc: Exception) -> str:
    """Why a port wouldn't open, in words. On Windows an open fails when another program holds the port."""
    text = str(exc) or exc.__class__.__name__
    return f"in use by another program? ({text})" if _winmm_indices() else text


class MidiDevices:
    def __init__(self, store) -> None:
        self._store = store  # the config store: ``settings.midi_devices`` is the list, ``save_settings`` writes it
        self._lock = threading.Lock()  # the list and the runtime state (short: never held while a port opens or closes)
        self._sync = threading.RLock()  # one look at a time: opening and closing a port is up to the driver and can be slow
        self._rt: dict[str, _Runtime] = {}
        self._subscribers: list[Subscriber] = []
        self._names: list[str] | None = None  # the port list of the last look (item 92: a change from the page reuses it)

    # -- the stream
    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def _dispatch(self, key: str, name: str, msg) -> None:
        """A message of an open port (the MIDI library's thread): counted, then handed to every subscriber."""
        rt = self._rt.get(key)
        if rt is not None:
            rt.received += 1
            rt.last = time.monotonic()
        for subscriber in self._subscribers:
            try:
                subscriber(key, name, msg)
            except Exception:  # noqa: BLE001 - one subscriber must never stop the others, or the port
                log.exception("MIDI message")

    # -- the list and the ports
    @property
    def _devices(self) -> dict[str, MidiDeviceSetting]:
        return self._store.settings.midi_devices

    def sync(self, names: list[str] | None = None) -> None:
        """Make the open ports match the list: add what is new, open what is on and plugged in, close what is off or
        gone. ``names``: the system's port list (read when not given; a listing that fails changes nothing: it must not
        be taken for "every controller was pulled"). Logs changes, not every try."""
        if mido is None:
            return
        with self._sync:
            if names is None:
                names = list_midi_inputs_checked()
                if names is None:
                    return
            self._names = names
            listed: dict[str, str] = {}
            for n in names:
                listed.setdefault(port_key(n), n)  # two ports of one key (a renumbered twin) are one device: opened once
            with self._lock:
                changed = self._migrate_locked(listed)
                for key, name in listed.items():
                    dev = self._devices.get(key)
                    if dev is None:
                        self._devices[key] = MidiDeviceSetting(name=name, input=True)
                        changed = True
                        log.info("MIDI device '%s' found: In is on", name)
                    elif dev.name != name:
                        dev.name, changed = name, True
                keys = list(self._devices)
            if changed:
                self._save()
            for key in keys:
                self._look(key, listed.get(key))

    def _migrate_locked(self, listed: dict[str, str]) -> bool:
        """The MIDI port of an earlier version (``midi_input``, a port name or part of one) is the device that was
        listened to: its In is on, and the setting is gone (the app listens to every device that is on)."""
        legacy = self._store.settings.midi_input
        if not legacy:
            return False
        name = match_port(legacy, list(listed.values()))
        key = port_key(name or legacy)
        dev = self._devices.get(key)
        if dev is None:
            self._devices[key] = MidiDeviceSetting(name=name or legacy, input=True)
        else:
            dev.input = True
        self._store.settings.midi_input = None
        log.info("MIDI port '%s' of an earlier version: that device's In is on", name or legacy)
        return True

    def _look(self, key: str, listed_name: str | None) -> None:
        with self._lock:
            dev = self._devices.get(key)
            if dev is None:
                return
            want_in, name = dev.input, listed_name or dev.name
            rt = self._rt.setdefault(key, _Runtime())
        if listed_name is None:  # not plugged in
            if rt.port is not None:  # pulled while open: the port object doesn't notice, the list does
                self._close(rt)
                rt.lost, rt.back = time.time(), None
                log.warning("MIDI device '%s' is gone from the system's list; it reconnects by itself when plugged in", name)
            rt.state, rt.error = "missing", None
            return
        if not want_in:
            if rt.port is not None:
                self._close(rt)
                log.info("MIDI device '%s': In is off, the port is released", name)
            rt.state, rt.error = "off", None
            return
        if rt.port is not None:
            rt.state, rt.error = "connected", None
            return
        previous = (rt.state, rt.error)
        try:
            rt.port = mido.open_input(listed_name, callback=lambda msg, k=key, n=name: self._dispatch(k, n, msg))
        except Exception as exc:  # noqa: BLE001
            rt.state, rt.error = "error", open_error_text(exc)
            if previous != (rt.state, rt.error):
                log.error("MIDI device '%s' failed to open: %s", name, rt.error)
            return
        if previous[0] in ("missing", "error"):  # it was not there, or would not open, and now it does
            rt.back = time.time()
            log.info("MIDI device '%s' is back", name)
        else:
            log.info("MIDI device '%s' opened", name)
        rt.state, rt.error = "connected", None

    @staticmethod
    def _close(rt: _Runtime) -> None:
        port, rt.port = rt.port, None
        if port is not None:
            try:
                port.close()
            except Exception:  # noqa: BLE001
                pass

    def _save(self) -> None:
        try:
            self._store.save_settings()
        except OSError as exc:
            log.warning("the MIDI devices could not be saved: %s", exc)

    def names(self) -> list[str] | None:
        """The system's MIDI input names at the last look, None before the first one (item 92)."""
        return list(self._names) if self._names is not None else None

    # -- what the page changes (applied at once)
    def set_switches(self, key: str, input: bool | None = None, output: bool | None = None) -> None:
        """Switch In and / or Out of a device. A closed In lets go of the port before this returns. KeyError: no such device."""
        with self._sync:
            with self._lock:
                dev = self._devices.get(key)
                if dev is None:
                    raise KeyError(key)
                if input is not None:
                    dev.input = input
                if output is not None:
                    dev.output = output
            self._save()
            # the list of the watchdog's last look: on macOS a list read on this (request) thread misses devices
            # plugged in since the start (item 92) and would close them as gone
            self.sync(self._names)

    def remove(self, key: str) -> None:
        """Take a device that isn't plugged in off the list (it is added again when it shows up). KeyError: no such
        device; ValueError: it is plugged in."""
        with self._sync:
            with self._lock:
                if key not in self._devices:
                    raise KeyError(key)
                rt = self._rt.get(key)
                if rt is not None and rt.state not in (None, "missing"):
                    raise ValueError("it is plugged in")
                del self._devices[key]
                self._rt.pop(key, None)
            self._save()

    def stop(self) -> None:
        with self._sync:
            for rt in list(self._rt.values()):
                self._close(rt)

    # -- what the pages show
    def status(self) -> dict:
        """``devices``: one entry per device of the list; ``connected_devices``: how many are open."""
        now = time.monotonic()
        with self._lock:
            out = []
            for key, dev in self._devices.items():
                rt = self._rt.get(key) or _Runtime()
                out.append(
                    {
                        "key": key,
                        "name": dev.name,
                        "input": dev.input,
                        "output": dev.output,
                        "state": rt.state or "missing",
                        "error": rt.error,
                        "received": rt.received,
                        "age": round(now - rt.last, 2) if rt.last is not None else None,
                        "reconnect": {"lost": rt.lost, "back": rt.back} if rt.back is not None else None,
                    }
                )
        out.sort(key=lambda d: d["name"].lower())
        return {"devices": out, "connected_devices": sum(d["state"] == "connected" for d in out)}

    def is_off(self, device: str) -> bool:
        """The device is in the list with In switched off."""
        with self._lock:
            dev = self._devices.get(port_key(device))
        return dev is not None and not dev.input

    def route_state(self, device: str) -> tuple[bool, str | None]:
        """For a route that names ``device``: (is it open, why not)."""
        key = port_key(device)
        with self._lock:
            dev, rt = self._devices.get(key), self._rt.get(key)
        state = (rt.state if rt is not None else None) or "missing"
        if dev is None or state == "missing":
            return False, f"no MIDI port matches '{device}'"
        if state == "off":
            return False, "its In switch is off (Connections → MIDI)"
        return state == "connected", rt.error if rt is not None else None
