# Fixtures

The fixture types: the editor for one model's channels, its modes and the imports.

[← All documentation pages](README.md)

![Fixtures page](../screenshots/fixtures.png)

The fixture types: everything shared by all fixtures of one model, one JSON file each in `config/fixtures/types/`.
- **Fixture types:** the list, with New, Duplicate, Rename and Delete. Renaming updates every rig that uses the type; a type that a rig uses can't be deleted.
- **Import OFL…** (also File → Import Fixture → Open Fixture Library…): turns a fixture of the [Open Fixture Library](https://open-fixture-library.org) into a type, from a downloaded `.json` file or online by manufacturer and fixture. A report shows what was taken, what was left out and why, and the assumptions, before anything is saved; see [Importing from the Open Fixture Library](fixture-library.md#importing-from-the-open-fixture-library). Desktop only: a device on the network can't import (the button is off there).
- **Import QLC+…** (also File → Import Fixture → QLC+…): turns a [QLC+](https://qlcplus.org) fixture definition (`.qxf`) into a type, from a file or from the QLC+ folders on this computer; the heads of a pixel bar become pixels, 16 bit and switching channels are read as in the Open Fixture Library, and what can't be used is reported and kept; see [Importing from QLC+](fixture-library.md#importing-from-qlc). Desktop only.
- **Links and source:** a type that came from the Open Fixture Library shows its manual, product page and video links and where it came from, under the type's settings.
- **Fixture library:** ten ready-made types come with the app (listed under [Fixture library](fixture-library.md#fixture-library)); like every shipped type they can be edited (your copy goes to your data folder) and reset to default.
- **Type editor:** description, output (DMX or the PitchPlease v2 serial protocol), gamma and the strobo colour (HSB). Below that are the **channel modes**, one section per mode (at least one): a name (as the fixture's display or manual calls it, e.g. 6CH), the **pixel count of that mode** (a bar can have 1 pixel in one mode and 8 in another; the PitchPlease v2 serial type keeps one Pixels field above), a short description and the channel layout in DMX order. Each channel is a constant (e.g. master = 255), a macro (e.g. a strip dimmer following "Dimmer 01"), a shutter (open / strobe values) or the pixel block (I, RGB or RGBW; **I** is one brightness channel per pixel, the brightest of its R, G and B, for a single-colour light such as a white or UV spot or a dimmer channel). ↑ ↓ ✕ reorder and remove channels.
- **Modes:** **Add mode** appends a copy of the last mode (a new mode is mostly the old one with a channel more or less); **make default** marks the mode a new rig fixture starts in; **✕ delete mode** removes one (not the last). A mode that fixtures of the active rig run in asks first and names them; they move to the default mode (the rig then has unsaved changes). Two modes with the same name get a warning.
- **Channel map:** the resulting DMX channels of every mode with their numbers, the total, and how many fixtures of the type fit one universe.

Edits apply to the lights right away and mark the type unsaved; Save writes the file, Revert reloads it.
