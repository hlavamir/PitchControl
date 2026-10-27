# General

The page for playing the show: macros, functions and masks, scenes, the scene preview and the audio analysis.

[← All documentation pages](README.md)

![General page](../screenshots/general.png)

The page for playing the show:
- **Macros:** 16 faders for strobo decay, idle attack, the two mask parameters, the two group colours (hue / saturation), audio reactivity and the strobo / idle brightness of each group. They map to the Launch Control XL's bottom knob row and faders.
- **Functions and masks:** manual strobo, fog, invert discoball, vertical symmetry, auto colour, swap colours, and the four masks A–D: Gradient, Back & Forth, Rotating Line and Noise.
- **Scenes:** the 8 scenes. ⏎ loads one, Shift + ⏎ (or save mode) stores the current macros into it, delete mode empties a slot. An empty slot loads the default values; no scenes ship with the app.
- **Scene:** a live preview of the mask with every fixture pixel in the colour it is sending. Below it the **Mask Curve** fader (0.25 to 4, 1 in the middle, a logarithmic scale; the mask is raised to this power before each fixture's own idle remap curve, so above 1 the scene gets darker and below 1 brighter, and the preview shows it; a macro like the others: saved in scenes, mappable to a MIDI control with Learn, keys ↑ ↓, double-click resets to 1; it was a field of the rig file up to 1.8.2, an old rig's value starts the macro once at `2 ^ value`). Then the phase bar: strobo drains it after each peak, idle fills it back. Then the final colours of groups A and B.
- **Audio:** the 32 frequency bands as columns (as in the vvvv patch: each band's own decaying maximum faint, the live value, its own minimum brightest) with the peaks map that triggers the strobo.
