# Changelog

All notable changes to PitchControl. Versions follow [semantic versioning](https://semver.org/):
**major** = old config files (rigs, fixture types, settings) no longer load, **minor** = new
features, **patch** = fixes only. Releases are tagged `vX.Y.Z`.

## Unreleased

### Added
- **MIDI routes with Learn per channel** (Control Desk → Routes → Add MIDI route): a route can take its values from a MIDI device instead of Art-Net or the DMX input. It has a MIDI device and MIDI channel, and **each of its output channels has its own input**: a CC (0–127 scaled to 0–255), a 14-bit CC pair, a note (velocity, or on / off), or a constant value as the fallback; up to 64 channels. **Learn is one button per channel:** click it, move a knob or press a key on the device, done (no walking through the channels; ends after 20 s; a control heard on another MIDI channel is reported). **Overlap notice:** when the learned control is also in the app's MIDI mapping, the page says so ("CC 21 on <device> also drives Strobo Decay in the MIDI mapping: both will react"), a warning, not a block. Same three layers (the app's output → routes → manual overrides) and hold-last-value as the other routes; a control that hasn't been touched yet writes nothing. The controller's own MIDI port is shared with the routes (its input hands every message on), any other device is opened for the routes that name it. `PATCH /api/routes/{id}/channels/{n}`, `POST /api/routes/{id}/learn`.
- **Routes on the Control Desk:** live input overrides output channels. A route copies a block of an Art-Net universe (or of the DMX input, both from the Inputs page) onto output channels: source, first input channel, count (1 to 512, so a whole universe is one row), output universe, first output channel; on / off and a name. **Three layers, the later one wins: the app's output (fixtures, fog) → routes → manual overrides.** A manual value on a routed channel sits on top and doesn't delete the route; releasing it shows the route again. **An input that stops keeps its last values** (an overridden channel stays overridden); a route lets go when it is switched off or removed. Routed channels are blue on the Control Desk (apart from the overrides), the header counts them next to "N overrides", and two routes on one output channel are reported (the later one wins). A new route starts off. Saved across restarts in `state/routes.json`; the engine copies the latest values in at frame time (at most one frame of delay). `GET`/`PUT`/`POST /api/routes`, `PATCH`/`DELETE /api/routes/{id}`.
- **Art-Net and DMX input** (Inputs → **04 / Art-Net / DMX input**): the app can receive DMX from outside, the first part of live input that overrides output channels (routes follow). **Art-Net:** a UDP listener on port 6454 (the standard; a port setting for another Art-Net program on the same computer, which shares it) on all network adapters or one chosen adapter; it keeps the latest 512 values of every universe it receives (the raw 15-bit port address, net / sub-net / universe) with its sender, packets per second and last-seen time, and ignores the packets of PitchControl's own Art-Net output, so an output universe can't feed back. **DMX over USB:** an Enttec DMX USB Pro that receives (Enttec's "Received DMX" and "Change of State" messages); a Pro that receives doesn't send, so a device that is also an enabled output is refused with a message (the output wins). The values of a source are kept when it goes quiet. Per computer (`machine.json`, key `live_input`), changed only on the computer that runs PitchControl and applied at once (`GET`/`PUT /api/live-input`). `tools/live_input_sim.py` sends test Art-Net.
- **An Open Fixture Library export plugin** (not yet in OFL): `tools/open-fixture-library/plugins/pitch-control/` is a plugin laid out for OFL's `plugins/` folder that adds PitchControl to the "Download as…" button of OFL's fixture pages. For every fixture it writes the type file this version's File → Import Fixture → Open Fixture Library saves (all modes PitchControl can express, with the kept OFL data); `tools/ofl_plugin_check.py` runs OFL's CLI on the item 50 fixtures and more (or all ~650 with `--all`) and compares each file with the import's, and runs OFL's lint and export tests on the plugin. See the README next to the plugin, which also lists the steps to submit it to OFL.
- **The log of the current run inside the app:** Settings → **Log** (and **Help → Show log** in the menu bar, which opens Settings at it) is a read-only view of what the app and the engine report, as the log file has it (time, level, logger, message; a traceback under its line). **Errors are red, warnings amber, info in the normal text colour, debug dim.** It follows the newest line (**Auto-scroll**, on by default; untick it to stay where you are; scrolling up by hand pauses it, the checkbox shows that, and scrolling back to the end resumes), and **Copy** puts the lines on the clipboard as text, for a bug report. It keeps the last 2,000 lines; the history of the run is there when you open it, new lines arrive live. This computer only: a phone or tablet on the network gets no panel, no stream and a 403 from `GET /api/log` (the log carries paths and device names). Behind it: an in-memory handler next to the file handler (`logsetup.MemoryLogHandler`, the last 3,000 records of the run, the level a field of each record), `GET /api/log`, and the records sent over the live websocket in batches twice a second, only while the panel is open, so the engine is not slowed.
- **Import from the Open Fixture Library:** File → Import Fixture → Open Fixture Library… (and **Import…** on the Fixtures page) converts a fixture of the [Open Fixture Library](https://open-fixture-library.org) into a fixture type, from a downloaded `.json` file or online by manufacturer and fixture (read from OFL's GitHub at one commit; or paste the address of the fixture's page). Before anything is saved a report lists the modes taken, the modes left out with the reason, the assumptions and the reminder to check the type against the manual; a name that is already taken (a shipped type too) asks before it is replaced. The conversion is the one the shipped fixture library was made with (item 50), now part of the app (`pitchcontrol.ofl`). This computer only: a device on the network can't import.
- **Imports keep the original data.** A type from the Open Fixture Library keeps OFL's own keys under their OFL names (`shortName`, `categories`, `meta`, `links`, `physical`, `matrix`, `availableChannels`, `templateChannels`, …), OFL's mode list as `ofl_modes`, the OFL mode each PitchControl mode came from (`modes[].ofl_mode`) and a `source` block (OFL's key, commit or file, schema, converter version), so the original fixture can be rebuilt exactly from the type. They survive loading, editing and saving on the Fixtures page. The Fixtures page shows the type's manual, product page and video links and its source. The shape is described in `backend/src/pitchcontrol/ofl/importer.py` and the README (Importing from the Open Fixture Library).
- **Import from QLC+:** File → Import Fixture → QLC+… (and **Import QLC+…** on the Fixtures page; the old **Import…** button is now **Import OFL…**) converts a [QLC+](https://qlcplus.org) fixture definition (`.qxf`) into a fixture type, from a file or from the fixtures in QLC+'s own folders on this computer (when QLC+ is installed). The file is read the way the Open Fixture Library's QLC+ import does it, into OFL's fixture model, and then goes through the same converter, report and kept data as an OFL import (one mapping): channel and capability presets, 16 bit (fine) channels, `<Alias>` switching channels, wheels, physical data and the modes. **`<Head>` elements become pixels** (matrix and template channels; the mode has as many pixels as it has heads), where OFL's own importer only warns. What can't be used is listed in the import report: modes whose heads can't be pixels, a mode without heads that lists several RGB sets, and every element or attribute the OFL model can't hold. The type keeps the QLC+ file: `source.via = "qlcplus"` and `source.file`, and a key `qlcplus` with the creator, QLC+'s own type, the unused parts of the file and the file itself. Desktop only, like the OFL import. No QLC+ fixture file is shipped; the tests use definitions written for them. Checked on 658 definitions exported from the Open Fixture Library by its own QLC+ plugin: all read without error, and of the 1779 modes both routes convert, the pixel count and pixel format agree in all but 11.
- **Submenus in the menu bar** (File → Import Fixture ▸), in the app-drawn Windows menu (→ opens, ← or Esc closes, the keys as in any menu) and the native macOS one.
- A link of a fixture type (its manual, …) can be opened in the browser from the Fixtures page; besides the project's pages, only the web addresses the user's own types carry.

### Changed
- The ten shipped fixture types are regenerated in the new shape (the same modes and values; each now carries its Open Fixture Library data and, for the three built from manuals, the hand-written OFL-format data). `tools/fixture_library.py` runs on the app's import and keeps the OFL originals at the pinned commit in `tools/fixture_sources/ofl/` (offline, and what the tests check the types against).

### Fixed
- **No more system-looking controls.** The Auto-scroll box above the log (Settings → Log) was the operating system's own checkbox (blue and round on macOS); it is now the app's switch. The "inv" box of a MIDI mapping row is the app's square check. The arrow of every dropdown is the app's small triangle instead of the system's (the list that opens is still the system's). The MIDI port field of the mapping's Controller tab no longer opens the system's suggestion list: the connected ports are buttons under the field. A test keeps native checkboxes, radio buttons, date / colour inputs and datalists out of the sources.
- **Dialogs block the app underneath.** The Import Fixture dialog let the keys through when the focus was on the page behind it (a click on the dimmed area, Tab out of the dialog): the number keys changed the page, W A S D moved the selection. Now every modal dialog (Import Fixture, and the "Unsaved changes" question, which also gets a dimmed backdrop and takes Esc as Stay) uses one shared mechanism: no page keys, no W A S D, no Ctrl / ⌘ + S and no menu-bar keys reach the page, clicks outside do nothing, Tab goes round the dialog's controls, **Esc** closes it as Cancel and the focus returns to where it was. The macOS menu bar's page items (pages, Save, Import, Settings, Help, Show log) wait until the dialog is closed. UI scale (Ctrl / ⌘ + + − 0) still works.

## 1.7.1 — 2026-10-21

### Changed
- **Help page, About: tidier layout.** The version, the two folders, then two labelled rows of identical buttons (Feedback:
  Report a problem, Join the Discord; Project: Project on GitHub, Releases) instead of a button, a caption, a text link and
  two more links in a row; one short caption says what a problem report contains. The Ko-fi button on the same page is
  the same component. The keys, the footer tips and the links work as before.

## 1.7.0 — 2026-10-21

### Added
- **A menu bar in the desktop app: File, Edit, View, Window, Help.** File: Save (what the page's Save button does, nothing
  on a page without one), Open data folder, Open logs folder, Quit (asks first like the close button). Edit: Cut, Copy,
  Paste, Select All on the text field being typed in. View: the ten pages and Full screen. Window: Minimize, and Zoom
  (macOS) or Maximize (Windows). Help: Documentation (pitchcontrol.eu/docs), Keyboard shortcuts (the Help page),
  Report a problem, Join the Discord, About PitchControl (the Help page's About). On **macOS** it is the native menu bar, with
  About, Settings… (⌘,) and Quit (⌘Q) in the PitchControl menu and the usual keys: ⌘S, ⌘1 – ⌘9 for the pages (the plain
  1 – 9 still work; Help is the plain 0, ⌘0 stays the UI scale's 100 %), ⌃⌘F full screen, ⌘M minimize, ⌘X / ⌘C / ⌘V / ⌘A. On **Windows** the app draws it in its header row
  next to the logo, in its own look (no page loses height), with the keys next to the items and Windows' keyboard
  convention: Alt or F10 gives the menu the keys, Alt + the underlined letter opens a menu, the arrows move, ⏎ runs, Esc
  closes; AltGr doesn't open it, and while the menu has the keys they don't reach the page or a field. A browser, on the
  same computer or on a phone, shows no menu bar. Both are built from one definition (`backend/src/pitchcontrol/menu.py`),
  and an item does the same on both.
- **⌘S / Ctrl+S saves the page** (like its Save button), also while typing in a field.
- **A Help page (key 0)** with the keyboard reference, About (version, folders, Report a problem, Join the Discord, the
  project's links) and Support (Ko-fi), which were in Settings; Settings keeps Appearance, Engine, Network and App.
- **Help → About → Report a problem** opens a new issue on GitHub in the browser, filled in with the version, the
  system (the computer's operating system and its version) and where the UI was opened from (the desktop app, a browser on
  the same computer, or a device on the network), with the headings What happened, What you expected and Steps and a line
  asking for the newest log file (Settings → App → Open logs folder). Nothing is sent by the app: you see and edit the issue
  before submitting it. On a phone or tablet on the network the button is a plain link that opens on that device, and so
  are the About and Ko-fi links now (before, they first asked the computer and were refused, which a popup blocker could
  then stop). The repository has issue forms for a bug report with the same fields and for a feature idea, which
  points to Discussions → Ideas for voting. **Join the Discord**, next to the button, opens the PitchControl Discord
  (https://discord.gg/4nbBaQDKz4) for questions and chat.
- **A built-in fixture library: ten popular fixtures come with the app**, each with every DMX mode PitchControl can drive
  (pick the type on the Rig page, the mode as set on the fixture): Stairville LED Flood Panel 150, LED Bar 240-8 (also the
  Varytec Giga Bar Pix 8 RGB / Frost), xBrick Quad 16x8W RGBW, SonicPulse LED Bar 10, Eurolite LED PT-100-32 Pixel DMX Tube,
  Ape Labs Neon Tube PIX, Astera FP1 Titan Tube (the 7 profile tables people use), Cameo ROOT Par 6 (all 14 modes, with the
  delay variants), Cameo Q-Spot 40 and Stairville BTL-30. Pixel counts, strobe values and held constants are set per mode
  (a strobe's open and fastest values are the fixture's real ones, e.g. 0 and 250 on the ROOT Par and Q-Spot multifunction
  strobes). Most were generated from the [Open Fixture Library](https://open-fixture-library.org) (MIT licence; the notice
  is `config/fixtures/Open Fixture Library notice.txt`) and all were checked against the manufacturers' manuals; the PT-100/32,
  Neon Tube PIX and BTL-30 are not in the library and were built from their manuals. The conversion
  (`tools/ofl_convert.py`, `tools/fixture_library.py`) is kept for the next fixtures. Like every shipped type they can be
  edited (a copy goes to your data folder) and reset to default.

### Changed
- **The Cameo Q-Spot 15's modes are named as its display and manual print them:** 02CH, 03CH1, 03CH2, 04CH, 09CH (they were
  2CH, 3CH-1, 3CH-2, 4CH, 9CH), the same spelling as the new Q-Spot 40. Only the names change; the modes' ids, which rigs
  store, stay, so existing rigs load unchanged and send the same DMX.
- **The single-channel pixel format `R` is now called `I`** (one brightness channel). It never sent the red channel: it
  sends one value per pixel, the brightest of the pixel's R, G and B after gamma, so it can drive any single-colour
  light, a white or UV spot, or a dimmer channel. Only the name changes (the Fixtures page's format dropdown says
  "I (one brightness channel)"); a type file with `R` still loads, as `I`, and is written as `I` when you next save the
  type. An older version of PitchControl does not know `I`, so keep a copy of your types before going back.
- **The pixel count belongs to each channel mode, not to the fixture type.** Many lights change their pixel count with
  the DMX mode: a tube with 1, 8, 16 or 32 pixels, a bar with 1, 6, 9 or 18. A mode now has its own **Pixels** field on
  the Fixtures page (next to its name); the engine's pixel sampling, the channel count, the channel map, the Rig page's
  placement preview and the rig problem check all use the fixture's mode. Switching a fixture's mode on the Rig page
  keeps its position, rotation and length; the pixels are spread over the same length again. Fixture types you already
  have load unchanged: the old per-type count becomes the count of every mode, and the file is written in the new shape
  when you next save the type. The PitchPlease v2 serial type keeps one Pixels field. An older version of PitchControl
  reads a type file saved by this version as a one-pixel type, so keep a copy of your types before going back.

### Fixed
- **Quitting asks about unsaved rig and fixture type edits too**, whichever page is open: their edits are live in the
  engine and only Save writes the file, so quitting dropped them without a question (the Rig and Fixtures pages never
  told the quit guard; the server now does).

## 1.6.0 — 2026-10-20

### Added
- **Network switch: open the UI on a phone or an iPad** (Settings → Network, **Allow other devices on this network**). Off
  by default, with a plain warning that anyone on the network can then control the lights and change the rig. When it is
  on, PitchControl also listens on every network address of the computer, on one fixed port (a setting, default 8420; when
  another program has it, Settings says so and the port is never moved). It applies at once, without a restart. The page
  lists every address as a link with a Copy button and a QR code to scan with the phone. An optional **PIN** (4 to 8
  digits): a device that isn't this computer first gets a PIN page, then a cookie (30 days); the API and the live
  connection refuse it without. Five wrong PINs from one address make it wait, 30 seconds and then longer. This computer
  is never asked. A device on the network can't change the network settings or open folders and windows on the computer.
  The switch, port and PIN are per computer (`machine.json`). The PIN keeps visitors out; it is not strong security (the
  traffic is not encrypted). The command-line option `--host` is gone (it is ignored with
  a note in the log): the switch replaces it, and it put no PIN in front of the UI. New dependency: `ifaddr` (lists the
  network adapters).
- **Phone layout** for a phone that opens the UI over the network: the General page's macros as sideways sliders (01–16,
  in the computer's order), the scenes as a 4 × 2 grid with Save and Delete, the function and mask buttons, and the
  Dimmers page (a dimmer no fixture uses is greyed out), with two tabs at the bottom (in landscape, in the top bar). Every
  control is at least 44 px, nothing depends on hovering, the text is larger than on the computer, and the ink, glow and
  brightness of Settings → Appearance apply. The scene preview and the audio meters are left out; Fixtures, Rig, Inputs,
  Outputs, Fog, Settings and the Control Desk stay on the computer (a link to one of them shows a note). "Full UI on this
  phone" switches the phone to the whole UI and "Phone layout" back; the phone remembers it. The layout follows the
  screen size, not the browser: a screen whose shorter side is below 600 px is a phone, so an iPad and the computer keep
  the full UI. The phone doesn't receive the scene preview (`/ws?preview=0`): less traffic on the wifi, and no extra
  preview rendering on the computer for each phone.
- **Open DMX interface: "Log frame timing"** (Outputs page, the interface's Advanced settings, off by default). For
  finding out why the lights go dark for a frame now and then on a bare Open DMX interface. While it is on, the log
  file gets one line every 10 seconds (frames per second, the longest write, the largest gap between two frames,
  frames dropped before they were written) and one line for each frame that came more than twice the frame time after
  the one before. Nothing is measured or written while it is off.
- **Channel modes per fixture type** (the model, the engine, the Rig page and the Fixtures page editor). Most DMX
  lights run in several channel modes (3CH, 4CH, 6CH, 9CH …); until now every mode needed a type of its own. A fixture
  type now holds one or more modes, each with a name, a short description and its channel layout, and one of them is the
  default; the pixel count, gamma and strobo colour stay per type. On the Rig page each fixture picks its mode in a
  **Mode** dropdown next to Type (shown for a type with more than one mode, "multiple" when several fixtures differ);
  the address checks ("overlaps", "beyond 512"), the channel map, the output monitor and the DMX output follow the
  fixture's mode. A new fixture starts in its type's default mode, and changing the type resets the mode to the new
  type's default. The mode is part of the rig, not of scenes. It is saved in the rig file as the mode's stable `id`, so
  renaming a mode never breaks a rig; a fixture without a mode uses the default, an unknown one is listed as a rig problem
  (and noticed on load) and plays in the default mode.
- **Fixtures page: the channel layout is a list of mode sections.** Each mode has a name, a short description and its own
  channel editor; **Add mode** starts as a copy of the last mode, **make default** marks the mode new fixtures start in,
  **delete mode** removes one (not the last). Deleting a mode that fixtures of the active rig run in asks first and names
  them; they move to the default mode and the rig shows unsaved changes. Two modes with the same name get a warning. The
  Channel map shows every mode.
- **Shipped types with modes:** **Cameo Q-Spot 15** now has its five modes (2CH, 3CH-1, 3CH-2, 4CH, 9CH, default 4CH as
  before) and a new **Eurolite LED 4C-7** type has 3CH, 4CH, 5CH, 6CH and 9CH (default 4CH). Modes without colour mixing
  (the Cameo's 2CH and 3CH-1, the Eurolite's 5CH) send the brightness on the dimmer channel and hold the colour macro at
  White; the 5CH and 9CH preset-colour, program and speed channels are named constants a fixture can override. If you
  have your own saved copy of Cameo Q-Spot 15 (marked **mod**), press **Reset** on the Fixtures page to get its modes.

- **A mask curve for the whole rig** (Rig page, Rig panel, under the description). One number from -3 to +3 bends the
  brightness curve of the mask for all fixtures at once: it is applied before each fixture's own idle remap curve, so
  the two add up (`mask ^ 2^(rig curve + fixture curve)`). 0 is as before, so existing rigs and scenes look the same.
  It is saved in the rig file as `mask_curve` and applies live.

### Changed
- **Keyboard navigation on the pages Fixtures, Rig, Inputs, Outputs, Fog and Settings.** Every control can be reached and
  used with the keys, without a mouse. The keys only navigate and never change a value by themselves: **W / S** or **↑ / ↓**
  move the highlight to the control above / below, **A / D** (or **← / →**) along a row, and **A** at the left edge, or **Esc**,
  takes it away (on the Rig and Fixtures pages it goes back to the list). The highlighted control looks like the selected one
  on the other pages. **⏎ starts editing** it: a number or text field gets the caret, a dropdown opens, a slider takes the
  focus, a button is pressed, a switch or checkbox toggles. While editing, the keys are text and ↑ / ↓ change a number (or a
  slider) as before, and **⏎ or Esc stops editing** and keeps the value. A click into a field edits it at once. The footer
  names the keys of the highlighted control and of an edited one.
- **Rig and Fixtures pages: the lists work like files in Finder or Explorer.** **W / S** or **↑ / ↓** select the next fixture
  (the Rig page) or fixture type (Fixtures); at the first or last one the keys carry on to the controls above or below the
  list. **D** or **→** goes into the details. On the Rig page **Shift** with the movement keys extends the selection as a range
  from the anchor, by the same rule as Shift + click, and **Space** adds or removes the current fixture without moving. ⏎ does
  nothing on the list (on a focused list button it no longer selects that fixture alone, which would throw away a range). The
  list has a thin outline on the current fixture when it is not selected.
- **Settings page: the keyboard reference has one line per key, and the page fits 1512 × 915 again** (the Network section and the longer key descriptions had pushed the About box below the window).
- **Settings: the Glow and UI brightness sliders can be focused (Tab, or ⏎ when highlighted) and changed with the arrow
  keys** (Shift = fine). The Settings page no longer has the one-control-always-selected grid; every control on it, including
  the Engine frame rate, the Network section and the links, can be reached by the keys.
- **Rig page, fixture list: Shift + click selects a range, ⌘ / Ctrl + click adds or removes one fixture.** Shift + click
  selects every fixture between the one you clicked last and the one you click now, in the order the list shows
  (alphabetical); ⌘ (macOS) or Ctrl (Windows) + click does what Shift + click did before. ⌘ / Ctrl + Shift + click adds a
  range to the selection.
- **Rig page, placement view: the first pixel's mark is drawn on top of all pixels.** On a short strip, where the
  pixels overlap, the ring round the first pixel is no longer covered by the pixels drawn after it. It is now a wider
  ring round the pixel; a selected fixture has a thin ring round every pixel, and its first pixel keeps the wider one.

### File format
- **Fixture type files have `modes` and `default_mode` instead of `channels`** (1.6). Old files keep working: a bare
  `channels` list loads as one mode, named by its channel count, and is written in the new shape when the type is saved.
  Old rigs have no `mode` and use each type's default mode, so a rig and a type folder from 1.5 load and play unchanged.
  An older app reads a new type file as one RGB pixel block, so keep a copy of your types before going back.

## 1.5.3 — 2026-10-17

### Changed
- **Audio normalisation is shared by all bands again, as in the vvvv patch.** The 32 bands used to be scaled each by
  its own maximum (1.0 to 1.5.2), which made a quiet band as full as a loud one. Now the loudest band sets the scale
  for all of them, so quiet bands (mids, highs) stay quiet next to the bass, as they were in vvvv. The band meter shows
  less in the mids and highs, and the masks that follow the sound react more to the low end; peaks are still found per
  band, against that band's own recent maximum. The normalisation settings (`normalisation_decay`,
  `normalisation_floor`) are as before.
- **Vertical Symmetry mirrors the left half of the image onto the right half**, as it did in vvvv before the averaging
  was added there: the left side is untouched and the right side is its mirror image. Up to 1.5.2 it averaged the image
  with its mirror image instead, which blended the two sides.

## 1.5.2 — 2026-10-16

### Added
- **OSC output** (Outputs page, section 04; Live output is section 05 now): sends the **base colours A and B** over OSC
  (UDP) to one IP address and port, for example to MadMapper or Resolume. They are the colours the Hue / Saturation
  faders or Auto Color Change make (Swap Colors applied), before strobo, brightness, masks, dimmers and gamma. An
  Enabled switch, the IP address, the port, and a list of files that say what to send; a status dot (sending, no file,
  nothing to send, file problem, not sending) and a line with the number of messages.
  - The files are JSON arrays in the new `osc/` folder of your data folder (next to `controllers/`); three examples
    ship with the app (`Colors as RGBA`, `Colors as floats`, `Colors as integers`). Each entry has `what`
    (`color_a` or `color_b` with `.r`, `.g`, `.b` or `.rgba`), `address` and `format`: `.r` / `.g` / `.b` as `f` (float
    0-1) or `i` (integer 0-255), `.rgba` as `r` (the OSC colour: four bytes R, G, B, A with A = 255). Anything else in
    a file is ignored and counted on the page.
  - A message is sent when its value changes and everything again once a second. A file edited while the app runs is
    read again within a second; one that can't be read keeps the last good messages going and shows the error.
  - OSC runs on its own thread, so a dead receiver never slows the lights, and saving only OSC settings restarts only
    OSC (the DMX outputs aren't touched).

### Fixed
- **Windows: a MIDI controller picked under MIDI port keeps working when another MIDI device is plugged in or pulled.**
  Windows adds the port's index to every port name (`LCXL3 1 MIDI In 0`) and renumbers the ports when a device comes or
  goes; the controller was then taken for pulled and not found again until the app was restarted (1.5.1). A port is now
  found by its exact name, then, on Windows, by its name without the index, then by a part of the name (the controller
  file's); a number is no longer taken for the start of a longer one (`… In 1` is not `… In 10`). The MIDI port row says
  `(now …)` for a port that is open under another number, not `(not found)`.
- The device lists of the Inputs page can no longer overlap with a restart of the audio input in PortAudio (a lock
  around the re-initialisation and the queries), and when the lists can't be read in the background the warning is
  logged when it changes, not every two seconds.

## 1.5.1 — 2026-10-15

### Added
- **The audio input reconnects by itself** to the device you selected. If the interface is pulled out (or someone steps
  on the cable) during a show, the Inputs page shows the input as stopped ("'Komplete Audio 6' disappeared. Check the
  cable: it reconnects by itself when the device is back") and the meter drops to zero; when the device is back, the
  input runs on it again within a few seconds, with no button to press, and a line under the input channels keeps what
  happened (`lost 21:13:58 · back 21:14:05`). An interface that wasn't plugged in at the start is switched to when it
  appears. It only ever goes back to the device you selected, never to another one; with no device selected, a stopped
  input restarts on the system default (and the line names both devices, because that is where the device changes under
  you). A device that is there but can't be opened (another program holds it) is tried again every ten seconds.
  While the input is gone the lights keep their colours and the parts that follow the sound (the masks) as they were,
  and no new strobo or peak triggers come from the missing sound: the strobo fades and the idle look comes in, as when
  the music has no beats. The manual controls and MIDI keep working. The band meter on the Inputs page is dimmed and
  says "input stopped · lights hold the last look". When the sound is back the lights follow it again.
- **The MIDI controller reconnects by itself.** Plug it in after the app started, or pull the cable and plug it in
  again: the input opens on its port within a couple of seconds, with nothing to press. A cable pulled while the
  controller is in use shows "isn't connected" at once and lets go of any button that was held (a fog button goes
  off). A port that can't be opened (another program holds it) is tried again until it is free. The Inputs page keeps
  a line of what happened (`lost 21:13:58 · back 21:14:05`, or `not found at start · connected 21:14:05`).
- **The Inputs page keeps its lists current.** The audio devices, the MIDI ports and the controller files are read
  again every two seconds while the page is open, so a device you plug in is in the list a moment later and one you pull
  out is gone, with nothing to press, and the running input is not touched. The buttons "Rescan devices" and "Find new
  devices" are gone: they were only there because the lists went stale, and the audio and MIDI inputs reconnect by
  themselves now. The Device field names what "System default" is (`System default (MacBook Pro Microphone)`). Saving
  a device that was plugged in after the app started looks for it again itself.

### Changed
- **macOS build script:** everything the build prints, warnings and errors included, is also written to
  `build-macos.log` in the repo root (the latest run only, gitignored), with a header of the tool versions. The
  Terminal still shows it all, and a failed build ends with "BUILD FAILED" and the log's path. The package installs
  (`npm ci`, `pip`) no longer run quietly, so their warnings reach the log.

### Fixed
- **A MIDI controller that isn't found or can't be opened says so on the Inputs page**, as text under the MIDI port
  row (which port was looked for and what to do), not only in the status dot's tooltip.
- **A microphone with one input works as the audio input** (the built-in microphone, an iPhone microphone): a device
  with fewer inputs than the "Input channels" setting now runs on the channels it has instead of refusing to start. The
  setting stays as saved. The Inputs page says what the input listens to ("device has 1 input · using channel 1"),
  and shows as text why the input doesn't run or isn't on the device that was set (an interface that isn't plugged
  in: the system default is used, and it switches back by itself when the interface is plugged in). Before, only the
  status dot's tooltip said "stopped".

## 1.5.0 — 2026-10-15

### Added
- **MIDI mapping in the app** (Inputs page, section 03): one row per macro with the control that drives it, a **Learn**
  button (move or press the control), buttons and notes as well as CCs, encoders (three relative modes), a channel per
  control, "page" (the same fader drives other macros on the Dimmers page) and a **shift** button that changes what
  other buttons do (for example scene load / save on the same button). A control used twice where the page and shift
  settings overlap is warned about; the shift setting is checked first, then the page (shift and page, shift only, page
  only, neither), and the first in the list wins between identical settings. A macro on the same control as the shift
  button can never fire; both rows say so.
  - A button's release always goes to the mapping that got its press, so letting go of shift or changing the page while
    a button is held releases it properly (a fog button is switched off). Closing the input, for example when the
    mapping is saved, lets go of everything that is held.
  - While Learn waits, the shift button and the buttons you let go keep working. Learn never takes a shift button or the
    release of a button as the control; a control learned while the shift button is held gets "with shift" filled in.
    Learn takes the first control that arrives (the input itself picks it, so nothing is missed or taken twice),
    also when the shift button is one you changed and haven't saved yet, and it gives up after 20 seconds. Removing a
    row while Learn waits no longer sends the control to another row.
  - Learn notices when the controller sends on another channel than the file says and offers to change it. Changing
    the controller's channel on the Controller tab asks about controls that name the old channel themselves.
  - Learn only listens to the controller that is in use. For another controller, or after an unsaved change of the
    MIDI port, Learn says so and offers "Save and use this controller" in one click; when no MIDI port is open it says
    that (naming the MIDI port in Settings when one is set there, which wins over the controller file's), and the
    "nothing arrived" message tells the two cases apart.
  - Mappings are saved as your own copy of the controller file (the shipped one stays untouched; Reset brings it back),
    and can be created, duplicated and deleted. A controller file also has an author, description and contact, and
    records when and with which PitchControl version it was last edited. The Controller mapping list shows the name
    from the file.
- Changing the page with unsaved edits on Inputs, Outputs, Fog or the MIDI mapping asks whether to save, discard or stay
  (they used to be dropped silently); closing the browser tab asks too (not the desktop window). The controller in use
  is chosen in one place on the Inputs page, section 03 ("Use this controller", or "Stop using it" to use none and free
  the MIDI port for another program); section 02 only shows which one it is and keeps the MIDI port. Choosing a
  controller keeps edits you haven't saved yet (audio device, MIDI port).
- The shipped **Launch Control XL 3** mapping is the author's own current one: the faders and knobs, the switches on the
  top button row (with shift Mask A-D), scenes 1-7 saved on the bottom row (with shift loaded), Dimmer
  01-08 on the middle knob row (the top knob row is unused) and CC 52 as the shift button.

### Changed
- MIDI channels are counted from 1 to 16 everywhere, as on the controllers and in most software; the MIDI monitor used
  to show the raw message, which counts from 0 (channel 13 appeared as 12).
- **Value scaling for faders and knobs:** when a fader's position and the macro's value differ (after a page change, a
  scene load or a change on screen), the macro doesn't jump while you move slowly: it follows the fader proportionally,
  and both reach the end of the range together. A fast move across the macro's value picks the macro up where the
  fader lands (a jump), and it follows the fader 1:1 from there. Tapping shift (or changing the page) only starts it
  over for the controls whose mapping changes; a fader that does the same in both layers stays 1:1.
- Controller files are a flat list of mappings now (`mappings`, with `page` and `shift` per mapping); files in the old
  form (`pages`, `cc`) still load and are written in the new form when saved.
- **The mask macros are renamed:** the four presets are now **Mask A–D** (Gradient, Back & Forth, Rotating Line, Noise)
  and Shader Speed and Shader Param are **Mask Param A** and **Mask Param B**; "shader" and "preset" are gone from the
  app. Scenes, controller mappings, the autosave, fixture types, rigs and fog settings from earlier versions still load:
  the old names are read as the new ones, and a file gets the new names when it is next saved.
- The desktop app asks before it quits when an output is live (quitting stops the engine, so the lights freeze on their
  last frame) or a page has unsaved edits. Cancel keeps the window and the output running.
- Saving content that doesn't fit (a controller mapping without a macro, a rig or fixture type with a wrong value) says
  what is wrong (`mappings[3]: a mapping needs a macro`) instead of "Internal Server Error".

### Removed
- **The page knob** of the controller files (`page_knob`: a knob that stepped through the control pages). Pages are
  switched with the Page General / Page Dimmers macros (map a button or knob to them) or on screen. A controller file
  that still has a page knob loads without it and shows a notice naming the file until it is saved.
- **The old Launch Control XL 3 layout**: its knob CC 13 (top knob row) no longer switches pages and does nothing now
  (Dimmer 01-08 are on the middle knob row), and the button rows have mappings. A copy of the old file in your own data
  folder is not touched: use Reset (shipped controllers) or take over what you need from the new layout. If you use the
  shipped mapping (no copy of your own), one notice at the first start after the update explains the new layout;
  PitchControl keeps the version of the last start per computer for this.

## 1.4.1 — 2026-10-13

### Changed
- **Fog machines are part of the rig** (`fog_machines` in the rig file) instead of `settings.json`:
  each rig has its own, loading another rig switches them. The Fog page edits the active rig's
  machines; its Save writes only them into the rig file. Fog machines from an older `settings.json`
  are moved once into the user's rigs (and into a copy of the shipped rig if that one is active).
- **Default rig:** four RGB lights at addresses 3–12, two 20-pixel LED strips at 20 and 100, and one
  fog machine on channel 1. New fixture type **Generic Addressable LED Strip** (20 RGB pixels).
- **Rig page:** fixtures in alphabetical order (numbers in order, case ignored), as are the fixture
  types on the Rig and Fixtures pages; a taller description field; the Reset button fits.
- The resize handle of text fields (and the corner between two scrollbars) follows the dark scheme
  instead of the system's light grey.

### Added
- A fog machine on a channel that a fixture uses too is reported as a rig problem.

## 1.4.0 — 2026-10-12

### Changed
- **Folders:** the app's defaults (fixture types, MIDI mapping, the Default rig, settings) are now
  read-only inside the app; your data folder (`Documents/PitchControl`) keeps only what you made or
  changed, and this computer's files (`machine.json`, macro autosave, Control Desk overrides, logs)
  live in the app-data folder (`~/Library/Application Support/PitchControl`,
  `%LOCALAPPDATA%\PitchControl`), never in a synced Documents folder. A source run uses the repo's
  `data/` and never writes into `config/`.
- **Settings are sparse and split:** `settings.json` holds only what differs from the defaults (new
  defaults reach everyone); the audio input, MIDI port, outputs and appearance are saved per computer
  in `machine.json`.
- **No scenes ship:** an empty scene slot means the macro defaults, and a first start begins with
  them — a calm test pattern for setting up the DMX output (Strobo and Audio Reactivity at 0, preset
  Back & Forth, all dimmers 100 %).
- **Default rig:** four generic RGB lights instead of the PitchPlease rig; no fog machines by default.
- The data folder of 1.3 is moved into the new layout on the first start (untouched copies of the
  old defaults are dropped, your own files are kept).

### Added
- **Shipped vs your own:** rigs and fixture types that come with the app are marked; saving one keeps
  your copy, **Reset to default** removes it, shipped ones can't be deleted.
- **Delete mode** for scenes (empties a slot).
- **Self-healing:** a file that can't be read is set aside (`….json.broken-<time>`) instead of
  being overwritten, and the app's own version is used; a missing rig or controller mapping falls
  back; problems are shown in a notice at the top of the UI. Every saved file records the
  `app_version` that wrote it.
- **Open logs folder** (Settings → App); Settings → About shows the data and computer folders.

## 1.3.0 — 2026-10-11

### Added
- **Enttec Open DMX USB** (the cheaper interface in the blue case) next to the Enttec DMX USB Pro and
  compatibles. The app detects the type from the USB device ("Detected: …"); an Advanced area under
  each interface lets you set the type and the way the break is made by hand. The app makes the DMX
  signal itself for it (break, mark, start code), about 26 frames per second. Worked out on a Mac
  with `tools/open_dmx_probe.py`: RTS and DTR low, the break as one byte at 90000 baud, a drain
  between the steps.
- **Frame rate** dropdown on the Settings page (20 / 25 / 30 / 40 / 44 fps, default 40).
- **Support** section on the Settings page with the Ko-fi link.

### Changed
- **Hue / saturation faders** show their colour scale only while in use: under the mouse, dragged,
  selected with the keys, or for a few seconds after the value changed (MIDI, scenes); otherwise
  the usual ruler. The scale slides in from the left in a quarter of a second.
- **Channel values:** each cell is a passive mini fader, filling from the bottom with the value, with
  the text inverted where the fill is.
- **Header:** the "enttec" indicators say "dmx" ("dmx 1", "dmx 2" …).
- **Browser tab icon:** the app's pixel mark instead of Vite's bolt.
- **Settings page:** the Engine and Support sections sit under Appearance, so the page fits again.

## 1.2.2 — 2026-10-11

### Changed
- **New home:** PitchControl now has its own repository, github.com/hlavamir/PitchControl. Settings →
  About links there, release tags are `vX.Y.Z`, and downloads are on that repository's Releases page.
- **Default settings:** `config/settings.json` no longer names one particular Enttec device. Add your
  interface on the Outputs page (Add interface); a settings file you already have is not touched.

## 1.2.1 — 2026-10-09

### Fixed
- **First start:** with no saved macro values (a new checkout or install; the saved state is not in
  the repo) all faders started at 0, so the lights stayed dark. The macros now start with the values
  of scene 1.

### Changed
- **Windows build script:** the window stays open at the end, the output of every step goes to
  `build-windows.log` (the window shows the step names and, on a failure, the end of the log), and
  missing or too old Node.js (the UI build needs 20.19+ or 22.12+) and missing Python 3.11 / 3.12 are
  reported up front. The UI packages are reinstalled when the Node version changed (npm skips the
  build tool's platform binary under an old Node), and the Python environment is made with 3.12 or
  3.11 even when a newer Python is installed. On CI nothing changes (no pause, output on the console).
- **Fog page:** the long label "Every … for … seconds" was cut off. The timer is one row now
  (switch, every _ s for _ s); universe and channel, and on / off value, have their captions next to
  the fields; the name field fills the row.
- **Universe dropdowns:** every DMX universe field (Rig, Outputs, Fog) is a dropdown of the universes
  0–3, like the Control Desk's. A value outside that range in an older file is kept and shown as
  "not offered". The Art-Net universe on the wire is a dropdown of 0–15.

## 1.2.0 — 2026-10-09

### Changed
- **Full macro names on the General page:** the abbreviated labels ("Strobo br.", "Sat. A", …) are gone;
  a name too long for its column gets tighter letter spacing and then a smaller font, never a second
  line.
- **Settings format:** `outputs.enttec` in `settings.json` is a list now. Settings from 1.1.0 load
  as before, but a `settings.json` saved by 1.2.0 does not load in 1.1.0.

### Added
- **Up to 4 Enttec DMX USB Pro interfaces:** Outputs → Add interface / Remove; each interface has its
  own device and universe, and its own status dot in the header. Settings with a single interface
  load as before.
- **UI scale shortcuts:** ⌘ (macOS) / Ctrl (Windows) with + or =, −, and 0 for 100 %, saved like the
  Settings slider.
- **Context footer everywhere:** every control on every page now has a tip in the footer (rows,
  buttons, selects, text fields, status indicators, lists, meters, panels, the tabs), and Tab focus
  drives it like the mouse.
- **Context footer:** the key-hint footer lists the keys and mouse actions of the control under the
  mouse or selected with the keyboard, with a short explanation (what each macro does, which
  fixture a Control Desk channel belongs to, …).

## 1.1.0 — 2026-10-08

First public release. A cross-platform (macOS, Windows) port of the vvvv patch with a new UI.

### Added
- **Engine:** 40 FPS, 32-band audio analysis with an octave-weighted strobo trigger. It ports the vvvv
  patch's phase, strobo / idle and colour logic, the four mask presets (Gradient, Back & Forth,
  Rotating Line, Noise) with symmetry and crossfades, scenes and fog timers.
- **Outputs:** Enttec DMX USB Pro, Art-Net, PitchPlease v2 serial. Gamma is applied per channel, the
  same for every output; the PitchPlease v2 / v3 firmware decodes perceptual values itself.
- **Monochrome UI** in its own window (macOS / Windows) or the browser:
  - grey, amber or phosphor ink, glow, UI brightness, UI scale with "Fit window";
  - fully keyboard-driven;
  - custom full screen that covers the MacBook camera notch.
- **Pages:**
  - General, Dimmers (names, unused dimmers disabled);
  - **Fixtures** (fixture type editor with channel layout and channel map);
  - **Rig** (rig files and per-fixture values, multi-edit, overrides of type values);
  - Inputs (audio, MIDI monitor), Outputs, Fog, Settings;
  - **Control Desk** (manual override of any DMX channel, saved across restarts).
- **Novation Launch Control XL Mk3** mapping with General / Dimmers page switching.
- **Config** as plain JSON files (fixture types, rigs, controllers, scenes, settings), edited in the
  app or by hand; unknown keys are logged, never fatal.
- **Version** shown in Settings → About and in the log.

## 1.0.0 — 2026-10-05

First working port of the vvvv patch (not released): the engine, outputs and a first web UI.
