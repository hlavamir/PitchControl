# Changelog

All notable changes to PitchControl. Versions follow [semantic versioning](https://semver.org/):
**major** = old config files (rigs, fixture types, settings) no longer load, **minor** = new
features, **patch** = fixes only. Releases are tagged `vX.Y.Z`.

## Unreleased

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
