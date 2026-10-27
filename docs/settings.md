# Settings

Appearance, network access, the engine's frame rate and the log.

[← All documentation pages](README.md)

![Settings page](../screenshots/settings.png)

- **Appearance:** ink colour (grey, amber, phosphor), UI scale (with "Fit window" for small screens), the key-hint footer and, in the desktop app, **Start in full screen** (F toggles full screen at any time). All of it is saved and restored next session.
- **Network:** lets a phone or an iPad on the same network open the UI in its browser (see [Other devices on the network](network.md)).
- **Engine:** the frame rate.
- **Log** (under Network, in the right-hand column): the log of this run, read-only, as the log file has it: time, level, logger, message (a traceback under its line). **Errors are red, warnings amber, info in the normal text colour, debug dim.** The view follows the newest line: **Auto-scroll** is on by default, switch it off to stay where you are; scrolling up by hand pauses it (the switch shows that) and scrolling back to the end resumes. **Copy** puts the lines on the clipboard as text, for a bug report. The view keeps the last 2,000 lines of the run (the backend keeps the last 3,000 records: `logsetup.MemoryLogHandler`; `GET /api/log` gives them, new ones follow over the live websocket in batches while the panel is open). **Help → Show log** in the menu bar opens Settings at this panel. The panel is on this computer only: a phone or tablet on the network gets no panel and no stream (`/api/log` answers 403), because the log carries paths and device names. The log *file* (one per start, File → Open logs folder) is unchanged.

The keyboard reference, About and Support are on the Help page (9).
