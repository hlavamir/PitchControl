# Changelog

All notable changes to PitchControl. Versions follow [semantic versioning](https://semver.org/):
**major** = old config files (rigs, fixture types, settings) no longer load, **minor** = new
features, **patch** = fixes only. Releases are tagged `vX.Y.Z`.

## Unreleased

## 1.8.6 — 2026-10-27

### Changed
- **A missing audio device is looked for for one minute, then Look again** (item 100): while the saved audio device is missing or has stopped delivering, PitchControl looks for it every 5 seconds for one minute, and then stops (item 99 of 1.8.5 went on once a minute, which could still delay the light output). Connections → Audio then says "not found · stopped looking after a minute" and shows a **Look again** button: it looks once more, and when the device is there the input restarts on it. The line "lost … · back …" stays after that too. A stream that comes back by itself is still noticed at any time, and opening the Audio tab doesn't reconnect it.

### Docs
- **The README is now a short introduction for beginners, and the details are in `docs/`**: one page for each page of the app, the keys, the network, the folders and files, the fixture library and imports, and development (the standalone app and releasing a version), with an index in `docs/README.md`. Nothing was removed; the text moved.

## 1.8.5 — 2026-10-27

### Changed
- **The shipped MIDI mappings are named alike**: manufacturer and model, in the list and in the file name. The Kontrol F1's is now "Native Instruments Traktor Kontrol F1" (`NativeInstruments_TraktorKontrolF1.json`), like "Novation Launch Control XL 3" (`Novation_LaunchControlXL3.json`). Your own copy of the F1 mapping keeps the name it has.
- **Log frame timing says what else ran** (item 98): every late frame of an Open DMX interface now lists what the app was doing at the time, such as a garbage collection, the audio device lookup, a file write or the MIDI device scan ("meanwhile: gc gen2 1× 84 ms, audio device lookup 1× 1.6 s (running)"). While it is on, the engine also logs its own late frames and a summary every 10 seconds. A frame counts as late from 1.5 times the frame time (was twice), and the summary line counts the full garbage collections. For finding the occasional skipped frame on Windows.
- **A missing audio device is looked for less often, and at low priority** (item 99): while the saved audio device is missing, PitchControl looks for it every 2 seconds for the first minute, then once a minute (was every 10 seconds). The lookup runs at low priority, so it can't delay the light output. This was the cause of the occasional skipped frames on Windows, found with Log frame timing.

## 1.8.4 — 2026-10-25

### Added
- **The Launch Control XL 3 mapping is now `Novation_LaunchControlXL3`**, named like the Kontrol F1's, with Miro's newest version: the shift button on CC 44, and the bottom button row saves scenes 1–8 (CC 45–52; with shift: loads them). A setup that used the old name `lcxl3` is moved over by itself: your own changed copy `lcxl3.json` becomes `Novation_LaunchControlXL3.json` (still with Reset to default), and the active mapping follows.
- **A MIDI mapping for the Native Instruments Traktor Kontrol F1** (Miro's, "Kontrol F1"), next to the Launch Control XL 3's: knobs and faders for the strobo, idle, hue and audio macros, pads for Manual Strobo, Fog, Invert Discoball, Vertical Symmetry, Auto Color Change and Swap Colors, pads C1–D4 save (page deck A) and load (page deck B) scenes 1–8, the Mute buttons select Mask A–D (latching). It expects the F1 in MIDI mode with the PitchControl! template of NI Controller Editor, every control on channel 13. The template ships too, as `config/controllers/NativeInstruments_TraktorKontrolF1.nckf1`, to import in Controller Editor.
- **Check for updates** in Help → About (item 82), next to Releases: when pressed, PitchControl asks GitHub for the newest release and says whether yours is the latest, or shows the new version with its date, release notes and a **Download** button that opens the zip for this computer (macOS arm64, Windows x64) in the browser. Nothing is checked at start, and the app downloads and installs nothing itself; without internet it says it couldn't reach GitHub. `GET /api/update-check`.

### Changed
- **Latching buttons: every press counts** (item 97). Some controllers switch a button themselves (NI Controller Editor's "Toggle"): 127 on one press, 0 on the next. A mapping row has a new **LATCH** option for such a button: every press counts, whether it sends 127 or 0, so a mask, a scene or an on / off macro reacts on every press instead of every second one. Learn ticks it by itself when it recognises a latching button. On a macro you hold (Fog, Manual Strobo) a latching button can't be held: the row says so and suggests setting the button to Gate in the controller's software.
- **The MIDI mapping shows where each macro sits** (item 96): every row says its place on its page, for example "Swap Colors · button 06", "Strobo Decay · fader 01", "dimmer 03", "scene 4", so a button can be learned from the matching button of the controller. The rows are in the order of their places: faders 01–16, then the buttons 01–16, then the rest. The General page's buttons are numbered like its faders: 01–08 in the top row (functions), 09–16 in the bottom row (masks).
- **Learn recognises what a control sends** (item 93). After catching a control, the MIDI mapping's Learn watches it for a moment: a **gate** button (press and release), a **trigger** button (press only), a **latching** button (the device switches on and off itself), a **fader** or a **relative encoder** (and which kind). It sets the row's behaviour to fit the hardware and the macro: a gate on a hold macro (Fog, Manual Strobo) holds, on an on / off macro it toggles; a latching button makes the macro follow it; a trigger toggles an on / off macro (on a hold macro the row says it can't be held); an encoder gets its encoder type. When one press can't tell (a button with no release), the row asks "press it once more"; a knob that barely moved, "turn it a bit". The row shows what was found ("detected: gate button"); the behaviour stays changeable. The routes' Learn is unchanged.
- **Faders work at full resolution** (item 95): a fader's value is no longer rounded to 128 steps inside the app (dragging, Shift for fine, scenes); the arrow keys keep their steps, MIDI still moves in its 128 steps per CC, switches and buttons still snap. Mask Curve's default is now exactly 2.2.
- **Mask Curve starts at 2.2** (items 94, 95), a cheap sRGB-like curve (mid-tones darker). It is the default for a first start, an empty scene slot and a double-click on the fader. Your current value stays as it is, and scenes saved before Mask Curve existed still load with 1, the look they were made with.
- **macOS: a MIDI device plugged in while the app runs is found** (item 92). CoreMIDI only tells a process about new devices on the thread that made its first MIDI client; the app looked from another thread, so on the Mac a controller plugged in after the start never appeared (nor came back after a pull). All looks at the MIDI ports now happen on the MIDI watchdog's thread, the first one included, which runs its run loop while it waits; the page uses its last list.
- **MIDI routes by channel and CC / note, with Learn** (item 91). A MIDI route on the Control Desk has no device and no route-wide channel any more: each of its output channels has its own MIDI channel and CC / note, from any device whose In is on. Press Learn on a channel and move a control: its channel and CC or note are taken. Routes saved before keep working (the route's channel goes into each of its channels).
- **MIDI mappings by channel and CC / note** (item 90). A mapping answers to its channel and CC / note from any device whose In is on, whatever the device is called. It has a **default in channel** and a **default out channel** (for LED feedback, not used yet); each row uses the default or its own channel, and **Learn** sets the row's own channel when the control is on another one. The Controller subpage no longer has MIDI port, Connected and Channel: it shows the two default channels and two notes, **Designed for** (the device) and **Mode** (how it must be set up). The mapping editor saves every change at once too (no Save or Revert; a shipped mapping is copied on its first change and keeps Reset to default). A mapping file with the old `port_match` loads unchanged; its text becomes the Designed for note.
- **MIDI devices as a matrix** (item 89). Connections → MIDI lists every MIDI device of the computer with an **In** switch (and **Out**, greyed until LED feedback exists) and its state: connected, off, not plugged in, or an error (on Windows a device another program holds can't be opened). A device the app hasn't seen before starts with In on. Every device with In on is one input: the mapping, Learn, the routes and the **MIDI monitor**, which now shows every incoming message with its device, also with no mapping, and says why a message isn't mapped (e.g. "channel 5, mapping expects 13"). Switching In off releases the device at once, so another program can use it. Each device reconnects by itself when plugged in again. The "MIDI port" setting is gone: a port chosen there keeps its device on.
- **Connections saves and applies every change at once** (item 88): no Save, Revert or Apply on the page any more. A switch, list or button takes effect when changed; a text or number field (IP, port, gain, host) on Enter or when you leave it, and Esc puts the saved value back, so a half-typed address restarts nothing. Only the input or output that changed restarts. The MIDI mapping editor saves at once too (item 90).
- **Routed channels have a colour of their own for each ink** (item 87): teal with amber, lavender with phosphor, coral with grey (before: one cyan, close to the phosphor ink and stray next to the grey one).
- **The header's DMX and Art-Net dots light for the inputs too** (item 86): a dot is filled while an output is connected or an input received something in the last 2 s, so a computer that only receives shows them on. With no USB DMX output, the DMX input has the dot.
- **The audio bands as in the vvvv patch** (item 81). Every band display (General → Audio, Connections → Audio, the audio bubble) draws three layers per band: at the back, faint, the band's **own** decaying maximum (it jumps up with each new high and sinks by 0.998 per frame); in front, the live value; and at the bottom, brightest, the band's own minimum, its floor. 1.8.3's even block of the shared normalisation value is gone. The displays are redrawn with every engine frame (40 fps) and without easing: they get their own websocket feed (`audio_subscribe`, `{"type": "audio", "bands", "peaks", "max", "min"}`) while one is on screen, instead of the state at 15 Hz with an 80 ms tween. The state loses `band_levels` and `band_norm`. The segmented faders (General, Dimmers, Mask Curve, the phone layout), the phase and settings bars and the hue faders' colour scale are laid out the same way, in whole screen pixels: every segment and every seam the same at 125 % or 150 % display scaling and at any UI scale (before, seams came out as sharp 1-pixel lines or blurred 2-pixel bands, and the segments in two or three heights). The meters are drawn on a canvas in whole screen pixels, so every column and every gap has the same width at any display scaling (125 %, 150 % on Windows) and UI scale; as a grid of 1fr columns the gaps came out 1 or 2 pixels wide, or vanished at a UI scale of 90 %.

### Fixed
- **The pointer hand over everything clickable** (item 79): page and subpage tabs, buttons, switches, dropdowns, checkboxes and links show the hand in the apps and the browser (Tailwind's base styles had left them on the arrow); the drawn Windows menu too (its titles File, Edit, … and the items of an open menu); disabled controls and menu items and the faders keep their own cursors.
- **Windows: a clicked button no longer looks keyboard-selected** (item 85). On Connections, Fog, Rig and Settings, a button or tab that was clicked got the keys' double outline, because Chromium (the Windows app) focuses a clicked button and the page took any focus as the keys' selection; only a focus the keys give (Tab) does now. The Mac app was not affected.
- **Windows: the audio device list follows what is plugged in again** (item 84). The short-lived helper that lists the devices (items 32 and 34) took longer than its 2 s limit in the built Windows app (a frozen exe's start plus PortAudio going through every WDM-KS and Bluetooth device), so the app fell back to its own list, which doesn't see a device plugged in later. The limit is 10 s now, only one helper runs at a time (the Audio tab and the audio watchdog share its answer for 1.5 s), the helper no longer loads numpy, and the log says how long it took.
- **An Enttec Open DMX USB sends at most 30 frames per second** (item 35), while the Pro, Art-Net and the other outputs keep the app's frame rate. At 40 fps the lights on an Open DMX flashed dark now and then: a full frame with its break takes about 31 ms on Windows, so at 25 ms per frame the next break started while the interface was still sending the end of the last frame. The Open's writer now keeps at least 1/30 s between the starts of two frames and always sends the newest one. Connections → DMX & Art-Net says so on the interface's card when the app runs faster; the frame timing log reads "target 30.0, clamped from 40.0". The writer also waits until the previous frame's bytes, and the break byte, can have left the interface before it switches the port's speed (Windows reports them sent while the chip still holds them), and on Windows the app sets the system timer to 1 ms steps while it runs and times its outputs with the precise clock: the frame timing log's times were rounded to 15.6 ms before, and the 30 fps gaps came out as 31 or 47 ms (a visible skipped frame).
- **Windows: Detect automatically finds the Enttec Open DMX USB** (item 83). Windows reports no product name for FTDI interfaces, so the app took an Open DMX USB for a Pro and sent it Pro packets (no light until the type was set to Open by hand). When the USB names don't decide, the app now asks the interface once when the outputs start (the Pro's "get serial number" request): a Pro answers, an Open can't. The log says how the type was found. Also: a device calling itself "ENTTEC Open DMX USB" is an Open, not a Pro.

## 1.8.3 — 2026-10-24

### Added
- **Mask Curve, a macro in the General page's Scene section** (item 76). A fader under the scene view, **0.25 to 4, 1 in the middle** (logarithmic, so 0.5 and 2 are a quarter of the travel either side of 1 and the darkening isn't squeezed into a fifth of the fader). The engine raises the mask to this power, `out = in ** value`, before each fixture's own idle remap (their curves stay as they are): above 1 the mid-tones go darker, below 1 brighter, and **the scene view shows the curved mask**. It is a macro like the others: saved in scenes (a scene saved before has none and gets 1), MIDI Learn on the Connections → MIDI mapping page, keyboard (↑ ↓, Shift for fine, W A S D to get there), footer hints, double-click resets to 1. The state of macros that are logarithmic: `MacroDef.log_scale`.

### Changed
- **The rig no longer has a mask curve** (item 76): the Mask curve field is gone from the Rig page, the macro replaces it. A rig file with `mask_curve` still loads, without a warning: the first time, the macro Mask Curve starts at `2 ** mask_curve` (limited to 0.25 to 4, the same curve as before), a line in the log says so, and the rig file is written again without the key.
- **The scene view has no corner brackets** (item 77): the four marks round the scene view are gone (General, Rig). The view keeps its size; no fixture moves.
- **Connections → DMX & Art-Net reads inputs, outputs, live output** from left to right (before: outputs, inputs, live output); the section numbers follow the reading order (01 Art-Net input, 02 USB DMX input, 03 Art-Net output, 04 USB DMX output, 05 Live output), and the keys W A S D follow the layout.
- **Subpage tab rows without the Q / E labels, left-aligned with the page row** (Connections, Control Desk). Q / E still step through the tabs; they stay in the footer and the Help page. On the Control Desk the Universe selector moved from the left end of the row to the right, next to the override counts.
- **Control Desk → Routes is per universe.** The Routes subpage lists the routes whose output is the universe chosen with the Universe selector; a new route goes to that universe, so the output-universe field is gone from the form (the route still stores its universe, saved routes don't change); a line counts the routes on other universes ("3 more routes on other universes (1, 2)"). The Routes tab is set apart from the channel tabs by a wider gap.
- **The audio bands are plain columns, with the normalisation behind the live value** (item 75). Every band display (General → Audio, Connections → Audio, the audio bubble in the header) draws each band as one column, no horizontal block segments, as in the vvvv patch: in front, brighter, the band's live level; behind it, dimmer, the shared normalisation value, the slowly decaying maximum all bands are divided by (decay 0.998 per frame, floor 0.25), so you see how far the music is from the scale the lights work in: the loudest band touches the dim column, and when the music gets quieter the dim column sinks slowly while the live ones drop at once. A band that peaks glows; the dotted strobo weights stay; the peaks map is plain columns too. All displays share one component (`components/BandMeter.tsx`). The live state gets `band_levels` (the bands before the division) and `band_norm` (the shared maximum); `bands` is unchanged.

### Fixed
- **macOS full screen is the system's own** (item 78). The F key, Start in full screen, the green window button, ⌃⌘F and the system's **View → Enter Full Screen** (the only full-screen item in View on a Mac; the app's own is Windows only) all use the same native full screen: the window gets its own Space, the menu bar slides in at the top edge and the Dock at the bottom, the menu works as in every Mac app, and the header's bubbles and the hover hints react to the mouse after every entry and exit. 1.8.2's own borderless full screen (which covered the camera-notch strip) is gone on macOS: its menu bar could not be reached, and after toggling it a few times the web view lost its mouse hover for good. The cost: on a MacBook with a notch the strip beside the notch stays black and the picture is about 33 px shorter (949 instead of 982 high on the 14"; the layout is made for that). Windows keeps its own full screen and its drawn menu. The window comes back at its old size and place when full screen ends (the 3008-pixel-wide window after leaving a start-in-full-screen is gone with the old code).

## 1.8.2 — 2026-10-23

The first release with the changes below: 1.8.0 and 1.8.1 were tagged, but their builds stopped in the tests (see 1.8.1 and 1.8.0).

### Added
- **Detail bubbles on the header's indicators.** The mouse resting on FPS, audio, midi, dmx or art-net, or the keyboard focus on it (Tab), shows a small bubble below it; Esc closes it, a click still opens the Connections tab (FPS: Settings, the target frame rate). **FPS:** a perf meter like vvvv's, the frame times of the last 10 s as a rolling graph, so a frame drop shows as a spike, the engine's compute time brighter at the bottom, the target frame time as a line, and "38.9 / 40 fps, 3 drops in 10 s" (a drop: over 1.5 × the target time), the longest frame and the engine's share. **Audio:** the device, its channels, the level and the live bands. **MIDI:** a light per MIDI input (the controller, each route device) that flashes with every message, and the last three messages. **DMX:** a row per USB DMX interface (status, universe, frames per second, the error), the USB DMX input and the PitchPlease v2 serial output. **Art-Net:** a row per output target and per sender heard. No bubbles on a phone or touch screen. Behind the FPS bubble: the engine writes two numbers per frame into a fixed ring (`engine/perf.py`, the last 1,024 frames), and the websocket sends them only while the bubble is open (`perf_subscribe` / `perf_unsubscribe`: the last 10 s, then the new frames every 0.25 s); the other bubbles use the state the UI already receives.
- **Input and output arrows** on the section headers: **→]** an input (into the app: Audio input, MIDI controller, Art-Net input, USB DMX input), **[→** an output (Art-Net output, USB DMX output, Live output, OSC output, PitchPlease v2), the same arrows in the header bubbles and on the Control Desk's routes (Source, Out univ.). One icon component (`components/Icon.tsx`) draws them in the ink on the app's pixel grid.
- **MIDI routes with Learn per channel** (Control Desk → Routes → Add MIDI route): a route can take its values from a MIDI device instead of Art-Net or the DMX input. It has a MIDI device and MIDI channel, and **each of its output channels has its own input**: a CC (0–127 scaled to 0–255), a 14-bit CC pair, a note (velocity, or on / off), or a constant value as the fallback; up to 64 channels. **Learn is one button per channel:** click it, move a knob or press a key on the device, done (no walking through the channels; ends after 20 s; a control heard on another MIDI channel is reported). **Overlap notice:** when the learned control is also in the app's MIDI mapping, the page says so ("CC 21 on <device> also drives Strobo Decay in the MIDI mapping: both will react"), a warning, not a block. Same three layers (the app's output → routes → manual overrides) and hold-last-value as the other routes; a control that hasn't been touched yet writes nothing. The controller's own MIDI port is shared with the routes (its input hands every message on), any other device is opened for the routes that name it. `PATCH /api/routes/{id}/channels/{n}`, `POST /api/routes/{id}/learn`.
- **Routes on the Control Desk:** live input overrides output channels. A route copies a block of an Art-Net universe (or of the DMX input, both from Connections → DMX & Art-Net) onto output channels: source, first input channel, count (1 to 512, so a whole universe is one row), output universe, first output channel; on / off and a name. **Three layers, the later one wins: the app's output (fixtures, fog) → routes → manual overrides.** A manual value on a routed channel sits on top and doesn't delete the route; releasing it shows the route again. **An input that stops keeps its last values** (an overridden channel stays overridden); a route lets go when it is switched off or removed. Routed channels are blue on the Control Desk (apart from the overrides), the header counts them next to "N overrides", and two routes on one output channel are reported (the later one wins). A new route starts off. Saved across restarts in `state/routes.json`; the engine copies the latest values in at frame time (at most one frame of delay). `GET`/`PUT`/`POST /api/routes`, `PATCH`/`DELETE /api/routes/{id}`.
- **Art-Net and DMX input** (Connections → DMX & Art-Net: **Art-Net input** and **USB DMX input**): the app can receive DMX from outside, the first part of live input that overrides output channels (routes follow). **Art-Net:** a UDP listener on port 6454 (the standard; a port setting for another Art-Net program on the same computer, which shares it) on all network adapters or one chosen adapter; it keeps the latest 512 values of every universe it receives (the raw 15-bit port address, net / sub-net / universe) with its sender, packets per second and last-seen time, and ignores the packets of PitchControl's own Art-Net output, so an output universe can't feed back. **DMX over USB:** an Enttec DMX USB Pro that receives (Enttec's "Received DMX" and "Change of State" messages); a Pro that receives doesn't send, so a device that is also an enabled output is refused with a message (the output wins). The values of a source are kept when it goes quiet. Per computer (`machine.json`, key `live_input`), changed only on the computer that runs PitchControl and applied at once (`GET`/`PUT /api/live-input`). `tools/live_input_sim.py` sends test Art-Net.
- **An Open Fixture Library export plugin** (not yet in OFL): `tools/open-fixture-library/plugins/pitch-control/` is a plugin laid out for OFL's `plugins/` folder that adds PitchControl to the "Download as…" button of OFL's fixture pages. For every fixture it writes the type file this version's File → Import Fixture → Open Fixture Library saves (all modes PitchControl can express, with the kept OFL data); `tools/ofl_plugin_check.py` runs OFL's CLI on the item 50 fixtures and more (or all ~650 with `--all`) and compares each file with the import's, and runs OFL's lint and export tests on the plugin. See the README next to the plugin, which also lists the steps to submit it to OFL.
- **The log of the current run inside the app:** Settings → **Log** (and **Help → Show log** in the menu bar, which opens Settings at it) is a read-only view of what the app and the engine report, as the log file has it (time, level, logger, message; a traceback under its line). **Errors are red, warnings amber, info in the normal text colour, debug dim.** It follows the newest line (**Auto-scroll**, on by default; untick it to stay where you are; scrolling up by hand pauses it, the checkbox shows that, and scrolling back to the end resumes), and **Copy** puts the lines on the clipboard as text, for a bug report. It keeps the last 2,000 lines; the history of the run is there when you open it, new lines arrive live. This computer only: a phone or tablet on the network gets no panel, no stream and a 403 from `GET /api/log` (the log carries paths and device names). Behind it: an in-memory handler next to the file handler (`logsetup.MemoryLogHandler`, the last 3,000 records of the run, the level a field of each record), `GET /api/log`, and the records sent over the live websocket in batches twice a second, only while the panel is open, so the engine is not slowed.
- **Import from the Open Fixture Library:** File → Import Fixture → Open Fixture Library… (and **Import…** on the Fixtures page) converts a fixture of the [Open Fixture Library](https://open-fixture-library.org) into a fixture type, from a downloaded `.json` file or online by manufacturer and fixture (read from OFL's GitHub at one commit; or paste the address of the fixture's page). Before anything is saved a report lists the modes taken, the modes left out with the reason, the assumptions and the reminder to check the type against the manual; a name that is already taken (a shipped type too) asks before it is replaced. The conversion is the one the shipped fixture library was made with (item 50), now part of the app (`pitchcontrol.ofl`). This computer only: a device on the network can't import.
- **Imports keep the original data.** A type from the Open Fixture Library keeps OFL's own keys under their OFL names (`shortName`, `categories`, `meta`, `links`, `physical`, `matrix`, `availableChannels`, `templateChannels`, …), OFL's mode list as `ofl_modes`, the OFL mode each PitchControl mode came from (`modes[].ofl_mode`) and a `source` block (OFL's key, commit or file, schema, converter version), so the original fixture can be rebuilt exactly from the type. They survive loading, editing and saving on the Fixtures page. The Fixtures page shows the type's manual, product page and video links and its source. The shape is described in `backend/src/pitchcontrol/ofl/importer.py` and the README (Importing from the Open Fixture Library).
- **Import from QLC+:** File → Import Fixture → QLC+… (and **Import QLC+…** on the Fixtures page; the old **Import…** button is now **Import OFL…**) converts a [QLC+](https://qlcplus.org) fixture definition (`.qxf`) into a fixture type, from a file or from the fixtures in QLC+'s own folders on this computer (when QLC+ is installed). The file is read the way the Open Fixture Library's QLC+ import does it, into OFL's fixture model, and then goes through the same converter, report and kept data as an OFL import (one mapping): channel and capability presets, 16 bit (fine) channels, `<Alias>` switching channels, wheels, physical data and the modes. **`<Head>` elements become pixels** (matrix and template channels; the mode has as many pixels as it has heads), where OFL's own importer only warns. What can't be used is listed in the import report: modes whose heads can't be pixels, a mode without heads that lists several RGB sets, and every element or attribute the OFL model can't hold. The type keeps the QLC+ file: `source.via = "qlcplus"` and `source.file`, and a key `qlcplus` with the creator, QLC+'s own type, the unused parts of the file and the file itself. Desktop only, like the OFL import. No QLC+ fixture file is shipped; the tests use definitions written for them. Checked on 658 definitions exported from the Open Fixture Library by its own QLC+ plugin: all read without error, and of the 1779 modes both routes convert, the pixel count and pixel format agree in all but 11.
- **Submenus in the menu bar** (File → Import Fixture ▸), in the app-drawn Windows menu (→ opens, ← or Esc closes, the keys as in any menu) and the native macOS one.
- A link of a fixture type (its manual, …) can be opened in the browser from the Fixtures page; besides the project's pages, only the web addresses the user's own types carry.

### Changed
- **Connections: the Inputs and Outputs pages are one page with subpage tabs**, sorted by topic: **Audio · MIDI · DMX & Art-Net · OSC · Serial**. The Inputs page had grown too long to see the Art-Net / DMX input without scrolling; now no tab needs scrolling at 1512 × 915. **DMX & Art-Net** has what is sent on the left and what comes in in the middle, Art-Net above and USB below (the Art-Net input next to the Art-Net output, the Enttec Pro input next to the USB DMX outputs), and the live output on the right. **MIDI** has the controller and the MIDI monitor on the left and the MIDI mapping on the right; its table scrolls inside its panel. One Save / Revert for the settings of all tabs, at the right of the tab row (the inputs and the MIDI mapping save on their own, as before); Rescan USB devices on the DMX & Art-Net and Serial tabs. Nothing that was on the two pages is gone. **Q / E** step through the tabs and wrap around at the ends; the page remembers its tab, also across restarts. The status indicators in the header (audio, midi, dmx, art-net) now open their tab. Old links to `#Inputs` and `#Outputs` open the Audio and the DMX & Art-Net tab.
- **Control Desk: Routes is a subpage.** The Routes section sat below the faders and made them shorter (less travel per DMX step); it is now the ninth subpage, after the eight channel subpages, in the same tab row, and the faders take the full height of the page again. Q / E step through all nine and wrap around, so Q from 1–64 goes to Routes (before, Q / E stopped at the ends). The override and routed counts and Reset all stay in the row on both. On Routes the keys move from control to control as on a form page (W A S D, ⏎ edits).
- **Page keys:** with Inputs and Outputs merged, the pages are 1 General · 2 Dimmers · 3 Fixtures · 4 Rig · 5 Connections · 6 Fog · 7 Control Desk · 8 Settings · 9 Help; 0 opens no page. Help gets ⌘9 in the macOS menu bar (⌘0 stays the UI scale's 100 %). The menu bar's View menu, the footer, the Help page's key list and the docs say the same.
- **The network QR code** (Settings → Network) is drawn in the app's colours, inverted: modules in the ink (amber by default; it follows the chosen ink) on the dark ground, with the standard four-module quiet zone instead of two. The current iPhone and Android camera apps read inverted codes; some older or third-party scanners don't (the fallback would be amber modules on a light border). A test renders the code, inverts it back and decodes it with jsQR (a new dev dependency).
- The ten shipped fixture types are regenerated in the new shape (the same modes and values; each now carries its Open Fixture Library data and, for the three built from manuals, the hand-written OFL-format data). `tools/fixture_library.py` runs on the app's import and keeps the OFL originals at the pinned commit in `tools/fixture_sources/ofl/` (offline, and what the tests check the types against).

### Fixed
- **The release build installs pywebview for its tests.** Two tests of the native menu (Help → Show log, the File → Import Fixture submenu) import pywebview, which the test step didn't install, so the 1.8.0 build stopped before it built anything. `pip install -e "backend[dev]"` now brings pywebview along.
- **macOS full screen no longer hides the menu bar for good.** In PitchControl's own full screen (the one that covers the camera-notch strip) the File, Edit, View … menus could not be reached. The menu bar and the Dock are now auto-hidden: they slide in when the mouse reaches the top or bottom edge of the screen, as in other full-screen Mac apps, and the picture still fills the whole screen. Windows is unchanged (its menu is drawn in the app's header). A test checks the option values and that the window still covers the screen.
- **Settings fits a 14" MacBook** (1512 × 915, the size the layout is made for) without scrolling. The **Log** takes the right-hand column under Network instead of the full width below everything, and fills what is left of the window; **Start in full screen** is in Appearance; the **App** section is gone: Open data folder and Open logs folder were in the File menu already, and **Open in browser** (the third button) is now **View → Open in browser** on both platforms. The texts that sent you to "Settings → App → Open logs folder" (the bug report, the config notice) say File → Open logs folder.
- **No more system-looking controls.** The Auto-scroll box above the log (Settings → Log) was the operating system's own checkbox (blue and round on macOS); it is now the app's switch. The "inv" box of a MIDI mapping row is the app's square check. The arrow of every dropdown is the app's small triangle instead of the system's (the list that opens is still the system's). The MIDI port field of the mapping's Controller tab no longer opens the system's suggestion list: the connected ports are buttons under the field. A test keeps native checkboxes, radio buttons, date / colour inputs and datalists out of the sources.
- **Dialogs block the app underneath.** The Import Fixture dialog let the keys through when the focus was on the page behind it (a click on the dimmed area, Tab out of the dialog): the number keys changed the page, W A S D moved the selection. Now every modal dialog (Import Fixture, and the "Unsaved changes" question, which also gets a dimmed backdrop and takes Esc as Stay) uses one shared mechanism: no page keys, no W A S D, no Ctrl / ⌘ + S and no menu-bar keys reach the page, clicks outside do nothing, Tab goes round the dialog's controls, **Esc** closes it as Cancel and the focus returns to where it was. The macOS menu bar's page items (pages, Save, Import, Settings, Help, Show log) wait until the dialog is closed. UI scale (Ctrl / ⌘ + + − 0) still works.
- **QLC+ import on a Mac: every QLC+ fixture folder was listed twice** in the dialog. The check for a folder that is found
  under two spellings (`Fixtures` and `fixtures`) compared lower-cased paths, which only lowercases on Windows; on a Mac
  both spellings exist on the case-insensitive disk. A folder is now the same folder when the disk says so (its device and
  inode), on every system.

### Removed
- **The v2 indicator in the header.** The PitchPlease v2 serial output's status is a row of the DMX bubble (shown when the output is set up).
- **Settings → Appearance: Glow and UI brightness.** The glow stays at 100 % and the ink at its normal brightness, as everybody ran it (UI brightness only dimmed the ink, while the screen's own brightness does that better). Settings files that still carry the two keys (`ui.glow`, `ui.brightness` in `machine.json`, or a `settings.json` from before 1.4) load without a warning and are written back without them; a test covers both. Ink colour, UI scale and key hints stay.


## 1.8.1 — 2026-10-23

(not released) Tagged as `v1.8.1`, but the macOS build stopped in the tests (three tests failed on a Mac, one of them a real bug in the QLC+ folder list, fixed in 1.8.2); everything listed under 1.8.2 is its content.

## 1.8.0 — 2026-10-23

(not released) Tagged as `v1.8.0`, but the build stopped in the tests before it built anything; everything listed under 1.8.1 is its content.

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
