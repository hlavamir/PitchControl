# Connections

Everything that goes in and out of the app, one tab each: Audio, MIDI, DMX & Art-Net, OSC and Serial.

[← All documentation pages](README.md)

Everything that goes in and out of the app, one subpage tab per topic: **Audio · MIDI · DMX & Art-Net · OSC · Serial** (the row starts at the page row's left edge; Q / E step through the tabs and wrap around at the ends, the keys are in the footer; the page remembers its tab, also across restarts). The status indicators in the header (audio, midi, dmx, art-net) open their tab; the mouse over one, or the keyboard focus on it, shows its details (see [Using the UI](keyboard-and-mouse.md)). The section headers carry an arrow: **→]** an input (into the app), **[→** an output (out of the app); the Control Desk's routes have them on Source and First out. Every change on these tabs is written and applied at once, with no Save button (item 88): a switch, list or button when it changes, a text or number field on Enter or when you leave it (Esc puts the saved value back); only the input or output that changed restarts. No tab needs scrolling at 1512 × 915.

## Audio

![Connections page, Audio tab](../screenshots/connections-audio.png)

Device, input channels and gain, with the 32-band meter: each band is a column as in the vvvv patch: its own decaying maximum faint behind, the live value, its own minimum as the brightest core, redrawn every engine frame. The dotted line shows how strongly each band counts towards the strobo trigger. A saved device that is missing, or that stopped delivering, is looked for every 5 seconds for a minute (item 100; the input reconnects by itself when it is there, and a line under the device says when it was lost and came back); after that PitchControl stops looking, says so, and **Look again** looks once more. Opening the tab reconnects nothing.

## MIDI

![Connections page, MIDI tab](../screenshots/connections-midi.png)

On the left the **MIDI devices** of this computer (item 89): one row per device with an **In** switch (a device not seen before starts on), **Out** (greyed until LED feedback exists) and its state (connected, off, not plugged in, error; on Windows a device that another program holds can't be opened, and switching In off frees it). Every device with In on is one input. Below, the MIDI monitor: every incoming message of every device that is on, with its device, which macro it moved or why it was ignored ("channel 5, mapping expects 13"), also with no mapping in use. On the right the **MIDI mapping** (item 90; two ship with the app: the Novation Launch Control XL 3, and the Native Instruments Traktor Kontrol F1 in MIDI mode with the PitchControl! template of NI Controller Editor): one row per macro with its control (CC or note) and its channel (the mapping's default or its own), Learn (move a control: its CC or note and, when it differs from the default, its channel are taken), behaviour (fader, encoder, toggle, held, press), page and shift (one shift button). A mapping answers to channel and CC / note from any device that is on; the Controller subpage has the default in and out channels (out: for LED feedback, not used yet) and two notes, Designed for and Mode. Every change is saved at once, as your own copy of the controller file (Reset to default brings the shipped one back). Its table scrolls inside its panel.

## DMX & Art-Net

![Connections page, DMX & Art-Net tab](../screenshots/connections-dmx.png)

From left to right what comes in (the inputs), what is sent (the outputs), and the live output; Art-Net above and USB below, so the inputs sit next to the outputs of the same kind.

- **Art-Net output:** targets, the app's universe 0–3 → IP, with the Art-Net universe 0–15 on the wire.
- **Art-Net input:** DMX that comes in from another program or a console, for the routes of the Control Desk. It listens on UDP port 6454 (the standard; change it when another Art-Net program on this computer has the port without sharing it) on all network adapters or on the one you pick; PitchControl's own Art-Net output is ignored. A list shows each Art-Net universe that has sent something (the raw Art-Net port address, counted from 0), its sender, packets per second and when it was last seen.
- **USB DMX output:** up to four USB DMX interfaces (Add interface / Remove; each with its own device and universe; the type is detected, see [USB DMX interfaces](#usb-dmx-interfaces)).
- **USB DMX input:** an Enttec DMX USB Pro that receives (the Pro only; a Pro that receives can't send, so the same device can't also be an output, and the output wins).
- The values of an input are kept when the sender goes quiet. The inputs are per computer (`machine.json`, key `live_input`); their switches apply at once, only on the computer that runs PitchControl. `py tools/live_input_sim.py artnet` sends test Art-Net.
- **Live output:** what every fixture sends: pixel colours and, with "show channel values", the channel table.

**Rescan USB devices** (on the DMX & Art-Net and Serial tabs) looks for newly plugged-in interfaces.

## USB DMX interfaces

Pick the device and its universe; the app finds out how to talk to it from the USB device ("Detected: …" under it). Two kinds are supported:

| Detected as | Devices | How it works |
|---|---|---|
| **Enttec DMX USB Pro or compatible** | Enttec DMX USB Pro and Pro Mk2 (one universe), DMXKing ultraDMX Micro / Pro and other interfaces that speak the Enttec Pro protocol | The interface has a processor: the app sends one packet per frame over the serial port and the interface makes the DMX signal. Tried on hardware (Enttec DMX USB Pro). Also what the app assumes when it cannot tell. |
| **Enttec Open DMX USB (bare FTDI)** | Enttec Open DMX USB (the cheaper one in the blue case) and other bare FTDI + RS-485 dongles | No processor: the app makes the DMX signal itself on the serial port (250 kbaud, 8N2, break, start code 0, 512 channels). An Open DMX sends at most 30 frames per second, even when the app runs faster (a 512-channel frame and its break take about 31 ms; started sooner, the break cuts into the end of the last frame and the lights flash); the Pro, Art-Net and the other outputs keep the app's frame rate, and Connections says so under the interface. Tried on hardware on macOS; the lines RTS and DTR have to be low, which the app does. |

**Advanced** (under each interface, closed by default; a dot means something is set by hand): the interface type, if the detection is wrong or the interface is unusual, and for the bare FTDI type how the break is made. "One byte at a lower baud rate" is the default and the only one that works with the macOS driver; "the port's break line" can leave the dongle in a break that only unplugging clears. `tools/open_dmx_probe.py` tries the ways of driving such a dongle one by one, for a new computer or interface.

Not supported: interfaces that only work through their manufacturer's driver or software (Nicolaudie / Sunlite, ChamSys, Anyma uDMX and similar), and sACN. Art-Net covers every network node with an Art-Net input (DMXKing eDMX, Enttec ODE, …).

## OSC output

![Connections page, OSC tab](../screenshots/connections-osc.png)

The OSC tab of Connections sends the **base colours A and B** over OSC (UDP) to one IP address and port, for example to a video mapping program: the colours as the Hue / Saturation faders or Auto Color Change make them (Swap Colors applied), before strobo, brightness, masks, dimmers and gamma. Switch it on with **Enabled**, give the **IP address** (a broadcast address works) and **Port**, and choose a file under **Messages**. The status dot says *sending*, *no file*, *nothing to send*, *file problem* or *not sending* (with the reason in the footer).

What is sent is described by a JSON file in the `osc/` folder of your data folder (next to `controllers/`; the app ships three examples that are always listed). A file is an array of entries with three keys:

```json
[
  {"what": "color_a.rgba", "address": "/color_a", "format": "r"},
  {"what": "color_b.g",    "address": "/color_b/green", "format": "i"}
]
```

- `what`: `color_a` or `color_b`, plus `.r`, `.g`, `.b` or `.rgba`;
- `address`: the OSC address (starts with `/`);
- `format`: `.r`, `.g` and `.b` are one value, `f` (float 0–1) or `i` (integer 0–255); `.rgba` is one OSC colour, `r` (four bytes R, G, B and A = 255).

Everything else is ignored (and counted in the section: "2 ignored: …"). A message goes out when its value changes, and everything again once a second, so a receiver started later catches up. A file you edit while the app runs is read again within a second; one that can't be read keeps the last good messages going and shows the error. OSC is sent from its own thread: a wrong address or a dead receiver never slows the lights. Saving only OSC changes restarts only OSC, not the DMX outputs.

## Serial

![Connections page, Serial tab](../screenshots/connections-serial.png)

The PitchPlease V2 serial output (device, baud rate, mirror mode).
