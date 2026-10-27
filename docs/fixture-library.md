# Fixture library and imports

The ten ready-made fixture types, and importing fixtures from the Open Fixture Library and QLC+.

[← All documentation pages](README.md)

## Fixture library

Besides the generic types and the Cameo Q-Spot 15 and Eurolite 4C-7, ten popular fixtures ship ready to use, each with **all** the DMX modes PitchControl can drive (the pixel count, the strobe values and the held constants are set per mode), so borrowed gear can be put into a rig without typing channel layouts:

| Type | Modes |
|---|---|
| Stairville LED Flood Panel 150 | 3CH, 4CH, 8CH; default 4CH |
| Stairville LED Bar 240-8 (also the Varytec Giga Bar Pix 8 RGB / Frost) | 2CH, 3CH, 5CH, 24CH; default 24CH |
| Stairville xBrick Quad 16x8W RGBW | 4CH, 6CH, 8CH, 16CH, 18CH; default 18CH |
| Stairville SonicPulse LED Bar 10 (the Bar 05 shares its 4, 5, 6, 11CH modes) | 4CH, 5CH, 6CH, 11CH, 39CH; default 39CH |
| Eurolite LED PT-100-32 Pixel DMX Tube | 3CH, 5CH, 8CH, 48CH, 96CH; default 96CH |
| Ape Labs Neon Tube PIX | 4CH, 7CH, 32CH, 64CH, 128CH; default 128CH |
| Astera FP1 Titan Tube | the profile tables 1, 4, 5, 18, 19, 42, 43 (named by table number), default table 42 (16 pixels RGB) |
| Cameo ROOT Par 6 | 2CH, 4CH1, 4CH2, 5CH, 6CH, 8CH, 11CH, D3CH, D5CH1, D5CH2, D6CH, D7CH, D9CH, D12CH; default 8CH |
| Cameo Q-Spot 40 | 02CH, 03CH1, 03CH2, 04CH, 09CH (as the display prints them, like the Q-Spot 15); default 04CH |
| Stairville BTL-30 | 7CH; default 7CH |

Most were generated from the [Open Fixture Library](https://open-fixture-library.org) (OFL, MIT licence, pinned to one commit; its copyright notice is `config/fixtures/Open Fixture Library notice.txt`) and every one was checked against the manufacturer's manual. The Eurolite PT-100/32, the Ape Labs Neon Tube PIX and the Stairville BTL-30 are not in OFL and were built from their manuals with the same conversion. How a mode is read: R, G, B (W) channels become the pixel block (per pixel for a pixel bar; a warm white is the W); a strobe or shutter channel becomes a shutter with its real open and fastest strobe values (not always 0 and 255: the ROOT Par 6 and Q-Spot 40 multifunction strobes are open again above 250); the master dimmer is held at 255 when the mode mixes colours itself and is an `I` channel when it has no colour channels; amber, UV, programs, speed, sound, delay and mode-select channels are named constants at their "off" or colour-mixing value, and a colour preset that is a mode's only colour source is held at White. A mode PitchControl can't express (a dimmer, amber or strobe per pixel, pixels interleaved with other channels, effect and hue tables) is left out; the Titan Tube ships only the seven profile tables people use (1, 4, 5, 18, 19, 42, 43; the others are listed in the type's `_note`).

To add fixtures or move to a newer OFL commit, edit the list and `OFL_COMMIT` in `tools/fixture_library.py` and run it (`backend/.venv/bin/python tools/fixture_library.py`): it converts the OFL files (kept in `tools/fixture_sources/ofl/` at the pinned commit; `--refresh` downloads them again) with the app's own import (`pitchcontrol.ofl`, the one behind File → Import Fixture), applies the corrections that come from the manuals and writes the type files. Read its report: OFL is community-written, so each new type must be checked against its manual before it ships.

## Importing from the Open Fixture Library

**File → Import Fixture → Open Fixture Library…** (or **Import…** on the Fixtures page) converts one fixture of the [Open Fixture Library](https://open-fixture-library.org) (OFL, MIT licence) into a fixture type, with the same conversion the shipped library was made with (how a mode is read: see [Fixture library](#fixture-library)). It needs the computer that runs PitchControl: a device on the network can't import.

- **From a file:** a fixture's `.json` (on the fixture's page in the library: Download as → Open Fixture Library JSON, or the file from OFL's GitHub). Works offline.
- **Online:** the manufacturer and the fixture from the library on GitHub, or the address of a fixture's page. Everything is read at one commit (shown in the dialog and kept in the type); it needs the internet, so not at a gig. GitHub limits unauthenticated requests: if it says so, wait a while or use a file.
- **The report**, before anything is saved: the modes taken (with pixels and channel count), the modes left out and why (a dimmer or amber per pixel, effect tables, …), the assumptions (e.g. "no open range, open = 0"), the manual's links and the reminder to check the type against the manual: OFL's fixtures are written by volunteers. Then the type's name (a file name; OFL's manufacturer and fixture name are suggested) and **Import**.
- **A name that is taken** (in any letter case, a shipped type too) is named in the dialog with what would be overwritten (and the rigs that use it); you rename the import or **Replace** the type. A shipped type that is replaced gets your own copy (Reset brings the original back). Rigs keep using the name; a fixture whose mode is gone runs in the new default mode.

**What a type keeps of the original.** Imports keep as much of the original data as possible, even what PitchControl doesn't use, so that the fixture can be used again later (exports, updates, other programs). PitchControl's own format stays as it is; what it adds stays close to OFL's: where a key means what an OFL key means it has OFL's name and shape. In the type file:

| Key | What |
|---|---|
| `shortName`, `categories`, `meta`, `comment`, `links`, `helpWanted`, `rdm`, `physical`, `matrix`, `wheels`, `availableChannels`, `templateChannels` (and any other key of the fixture) | OFL's own top-level keys, under their OFL names, untouched. `links` (manual, product page, video) is shown on the Fixtures page |
| `ofl_modes` | OFL's own `modes` list, untouched (OFL's name collides with PitchControl's `modes`) |
| `modes[].ofl_mode` | the name of the OFL mode this PitchControl mode was converted from; modes that could not be converted are in `ofl_modes` only |
| `source` | `format` (`"ofl"`), `fixture` (OFL's key, `manufacturer/fixture`), `name` (OFL's own name), `manufacturer`, `url`, `schema` (OFL's `$schema`), `license` (`"MIT"`), `converter` (the version of this mapping), `key_order` (OFL's top-level keys in their order), and where this copy came from: `commit` (online), `file` (from a file), `schema_version` |

The original OFL fixture can be rebuilt exactly from the type file (`rebuild_ofl` in `backend/src/pitchcontrol/ofl/importer.py`, whose docstring is the complete description of the shape; a test does it for every shipped fixture). The kept keys survive loading, editing on the Fixtures page and saving: they are carried through, whatever you change. Edit PitchControl's own keys (modes, gamma, description), not the kept ones.

## Importing from QLC+

**File → Import Fixture → QLC+…** (or **Import QLC+…** on the Fixtures page) converts a fixture definition of [QLC+](https://qlcplus.org) (a `.qxf` file; QLC+ has thousands of them) into a fixture type. It is read the way the Open Fixture Library's own QLC+ import does it, into OFL's fixture model, and then goes through the same conversion, report and kept data as an OFL import, so there is one mapping to PitchControl. It needs the computer that runs PitchControl: a device on the network can't import.

- **From a file:** any `.qxf` (QLC+'s `Fixtures` folder, the QLC+ forum, a download). Works offline.
- **From QLC+ on this computer:** when QLC+ is installed, the dialog lists the fixtures of its folders (the installation's `Fixtures` folder and your own, e.g. `C:\QLC+\Fixtures` and `C:\Users\<you>\QLC+\Fixtures` on Windows, `/Applications/QLC+.app/Contents/Resources/Fixtures` and `~/Library/Application Support/QLC+/Fixtures` on macOS, `/usr/share/qlcplus/fixtures` and `~/.qlcplus/fixtures` on Linux; the QLC+ 5 and Program Files variants too) by manufacturer and fixture. Without QLC+ the dialog says so and you can still pick a file.
- **How the file is read:** channel presets (`IntensityRed`, `PositionPan`, …) and capability presets (`StrobeSlowToFast`, `ColorMacro`, …) become OFL capabilities, other channels are guessed from their group; **fine channels** (16 bit) become the coarse channel's fine aliases, **`<Alias>` switching channels** become OFL's switching channels (read with the controlling channel at its default, as for OFL fixtures); wheels, physical data, authors and the modes are mapped as OFL does it. **`<Head>` elements become pixels**, which OFL's own importer only warns about: a mode whose heads all have the same channels becomes an OFL matrix with template channels (`Red $pixelKey`, the head number is taken from the channel names, the pixel layout from the `Layout` of the physical data) and a matrix insert, so the mode has as many pixels as it has heads. A channel that several heads list is a plain channel (a master dimmer), heads that list the same channels are one pixel (OFL's pixel groups). A mode whose heads can't be pixels (different channels, not one block of the mode's channels, channels ordered per colour) is left out and the report says why; a mode without heads that lists several RGB sets is warned about (PitchControl takes the first as the pixel and holds the others at their default).
- **The report** is the OFL import's, plus what the OFL model can't hold of the file (an element or attribute nothing read: a focus type, a resource, …).

**What the type keeps:** the same shape as an OFL import (OFL's keys under their names, `ofl_modes`, `modes[].ofl_mode`, `source` with `format: "ofl"`, `via: "qlcplus"` and `file`, the QLC+ file's name; no `fixture`, no `license`: it is your own file) and a key `qlcplus`: `creator` (QLC+'s name, version and the author of the file), `type` (QLC+'s own type), `unmapped` (every element and attribute the reader did not use, with its path) and `xml` (the file itself). The OFL fixture the reader built can be rebuilt exactly from the type (`rebuild_ofl`), and the `.qxf` text is in the type, so nothing of QLC+'s data is lost. QLC+'s fixture files are not shipped with PitchControl (the licence of the individual files is not stated); the test definitions in `backend/tests/qlcplus/` were written for the tests.
