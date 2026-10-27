# Folders

Where the app keeps its defaults, your data and this computer's files, and what the files contain.

[← All documentation pages](README.md)

| Folder | Where | What |
|---|---|---|
| Defaults | inside the app (the repo's `config/`) | what ships: fixture types, MIDI mappings, the Default rig, default settings. Read-only. |
| Your data | `~/Documents/PitchControl/`; a source run: the repo's `data/` (gitignored) | only what you made or changed |
| This computer | `~/Library/Application Support/PitchControl` (macOS), `%LOCALAPPDATA%\PitchControl` (Windows); with `--data` or a source run: `.machine/` in the data folder | `machine.json`, `state/`, `logs/` |

Your data folder is chosen in this order: `--data <folder>`; a folder written in `~/Documents/PitchControl/data_folder.txt`; the repo's `data/` for a source run; `~/Documents/PitchControl`. A data folder that is (or contains) the app's own defaults is refused.

A file in your data folder wins over a default of the same name (ignoring case); lists show both. Saving a shipped rig or fixture type writes your copy; Reset to default deletes it. Every saved file records the version that wrote it (`"app_version"`).

| Path | Content |
|---|---|
| `settings.json` | the show's settings that differ from the defaults: frame rate (`fps`), active rig and controller, Auto Color palette, masks, audio analysis |
| `machine.json` (this computer) | what belongs to one computer: audio input (device, channels, gain), the MIDI devices (In / Out per device), outputs (up to 4 USB DMX interfaces, Art-Net targets, v2 serial, OSC), appearance (`ui`), the network switch with its port and PIN (`network`), the live input (`live_input`: the Art-Net port and adapter, the DMX input device) |
| `fixtures/types/*.json` | one file per fixture model (edited on the Fixtures page); missing keys get defaults; ten ready-made models ship, see [Fixture library](fixture-library.md#fixture-library); an imported one also carries the original data, see [Importing from the Open Fixture Library](fixture-library.md#importing-from-the-open-fixture-library) |
| `rigs/<name>.json` | fixture instances and fog machines (`fog_machines`, edited on the Fog page) for one event (edited on the Rig page): type, group A/B, universe/address, UV placement (rotation in degrees), dimmer, colour sources, overrides of type values as `{"enabled": …, "value": …}`; the dimmer names (`dimmer_names`) |
| `controllers/*.json` | MIDI controller mappings (CC or note → macro), edited in Connections → MIDI |
| `osc/*.json` | what the OSC output sends (what, address, format; see [OSC output](connections.md#osc-output)), edited by hand; the file is chosen in Connections → OSC |
| `scenes/scene_N.json` | the 8 scenes (macro name → control value); an empty slot means the macro defaults |
| `state/macros.json` (this computer) | auto-saved macro values, restored on start; without it (first start) the macro defaults |
| `state/overrides.json` (this computer) | Control Desk channel overrides, restored on start |

Unknown keys (typos) are reported in `logs/YYMMDD_hhmmss.log` (one file per start) and never stop the engine. Keys starting with `_` (e.g. `_note`) are annotations and are ignored. A file that can't be read is renamed (`….json.broken-<time>`, never overwritten), the app's own version of it is used where there is one, and the UI shows a notice. A missing active rig falls back to the Default rig, a missing controller mapping to none.

**From 1.3:** on the first start of 1.4 an old `Documents/PitchControl/config/` is moved into this layout once: `state/` and `logs/` go to this computer's folder, `settings.json` is split into the sparse show part and `machine.json`, and files identical to a version the app ever shipped are dropped (the current defaults apply). Your own files stay. A source checkout used the repo's `config/` as its data before; that setup is in git history (`git show v1.3.0:config/rigs/Default.json`) and can be copied into `data/` or `~/Documents/PitchControl/`.

A fixture type holds one or more **channel modes** (the DMX modes a device offers: 3CH, 4CH, 6CH …), each with an `id`, a `name`, a `description`, its pixel count `pixels` and its **profile**, the ordered `channels` list. `default_mode` is the id of the mode a new rig fixture starts in. Gamma and the strobo colour belong to the type and are the same in every mode:

```json
"modes": [
  { "id": "4ch", "name": "4CH", "description": "Red, green, blue, white", "pixels": 1, "channels": [{ "pixels": "RGBW" }] },
  {
    "id": "9ch",
    "name": "9CH",
    "description": "Master, strobe, colours",
    "pixels": 1,
    "channels": [
      { "name": "master", "value": 255 },
      { "name": "dimmer", "macro": "Dimmer 03" },
      { "name": "strobe", "shutter": { "open": 0, "strobo": 200 } },
      { "pixels": "RGBW" }
    ]
  }
],
"default_mode": "4ch"
```

A rig fixture names its mode with `"mode": "<id>"`. The id is what counts, so renaming a mode never breaks a rig; a fixture without `mode` runs in the type's default mode, and an unknown id is listed as a rig problem (the default mode is used meanwhile). Type files from before 1.6 have a bare `channels` list instead of `modes`: it loads as one mode named by its channel count (`4CH`) and is written back in the new shape when the type is next saved. A type file from before 1.6.1 has one `pixels` for the whole type: it becomes the pixel count of every mode (a mode's own `pixels` wins) and is written into the modes when the type is next saved. An older app reads a type file written by 1.6 as one RGB pixel block, and one written by 1.6.1 as a one-pixel type, so keep a copy of your fixture types before going back.

`value` is a constant (a rig can override it by name with `channel_values`). `macro` sends a macro's value as 0–255. `shutter` sends `strobo` on a peak frame when the instance has `real_strobo` enabled. `pixels` expands to pixel count × `I` / `RGB` / `RGBW`. `I` is one brightness value per pixel, the brightest of its R, G and B after gamma; it was called `R` up to 1.6, and a type file with `R` loads as `I` and is written as `I` when the type is next saved.

To re-import scenes and `macros.ini` from the original vvvv patch folder: `.venv/bin/python -m pitchcontrol.legacy --vl <folder>` (into the repo's `data/`; `--data` chooses another folder).
