"""Settings in layers: the model's defaults, the shipped ``settings.json``, the user's sparse
``settings.json`` and this computer's ``machine.json``.

Everything here works on plain JSON data (dicts, lists, scalars), so it is independent of the
pydantic models.

- ``merge``: a deep merge of dicts; lists and scalars are replaced as a whole.
- ``diff``: the smallest dict that turns ``base`` into ``new`` when merged onto it.
- ``split_machine``: the per-computer part of a settings dict and the rest (the show).
"""

from __future__ import annotations

import copy
from typing import Any

# What belongs to one computer rather than to the show, along whole sections: the audio input
# (device, channels, gain), the MIDI devices (item 89), every output (which interface sends which internal
# universe, Art-Net IPs, the serial port) and the UI (scale is per screen, brightness per booth).
# Which universe a fixture writes to stays in the rig. The network switch and its PIN are this computer's own
# too, and so is the live input (the Art-Net adapter and port, the DMX input device). ``None`` = the whole key.
MACHINE_KEYS: dict[str, set[str] | None] = {
    "audio": {"device", "channels", "gain"},
    "midi_input": None,
    "midi_devices": None,
    "outputs": None,
    "ui": None,
    "network": None,
    "live_input": None,
}


def merge(base: Any, over: Any) -> Any:
    """``over`` merged onto ``base`` (neither is changed)."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = copy.deepcopy(base)
        for key, value in over.items():
            out[key] = merge(out[key], value) if key in out else copy.deepcopy(value)
        return out
    return copy.deepcopy(over)


def diff(base: Any, new: Any) -> dict:
    """The keys of ``new`` that differ from ``base`` (recursively for dicts)."""
    out: dict = {}
    for key, value in new.items():
        if key not in base:
            out[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(base[key], dict):
            sub = diff(base[key], value)
            if sub:
                out[key] = sub
        elif value != base[key]:
            out[key] = copy.deepcopy(value)
    return out


def split_machine(data: dict) -> tuple[dict, dict]:
    """(show, machine): ``data`` divided along ``MACHINE_KEYS``."""
    show = copy.deepcopy(data)
    machine: dict = {}
    for key, sub in MACHINE_KEYS.items():
        if key not in show:
            continue
        if sub is None:
            machine[key] = show.pop(key)
        elif isinstance(show[key], dict):
            part = {k: show[key].pop(k) for k in list(show[key]) if k in sub}
            if part:
                machine[key] = part
            if not show[key]:
                del show[key]
    return show, machine


def has_machine_keys(data: dict) -> bool:
    return bool(split_machine(data)[1])
