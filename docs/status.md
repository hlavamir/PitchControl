# Status

What is covered by tests and what has been verified on hardware.

[← All documentation pages](README.md)

Working and covered by tests:
- config loading and typo reporting; the layered folders (defaults, your data, this computer), copy on save and reset, sparse settings, the 1.3 migration, broken-file handling;
- the v3 DMX frame (checked against the v3.2 firmware layout);
- Enttec Pro, Enttec Open DMX USB, Art-Net and v2.2 serial packet formats;
- the 32-band analysis with octave-weighted strobo trigger;
- the phase, strobo/idle and colour logic;
- the mask generators and noise port, crossfade and symmetry;
- scenes, the REST API and the WebSocket.

The UI runs against the engine at 40 FPS in no-hardware mode.

Verified on macOS: audio input and analysis (microphone test), the LCXL3 MIDI controller, and DMX output through the Enttec DMX USB Pro to one Cameo pinspot (2026-10-07). On a Windows laptop the app builds and starts (2026-10-09). **Not yet verified on hardware:** Art-Net and v2 serial output, several Enttec interfaces at once, and the Windows build with hardware connected. Fixture details and the LCXL3 mapping were confirmed by Miro on 2026-10-05.

The masks match the vvvv look so far, except that Back and Forth rotates in 45° steps (vvvv: 90°); left as is for now.
