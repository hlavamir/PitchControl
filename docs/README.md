# PitchControl documentation

The details behind the [README](../README.md): every page of the app, the keys, the folders and files, the fixture library and how to build the app. The website [pitchcontrol.eu/docs](https://pitchcontrol.eu/docs) has the guide for using it.

Audio-reactive light control for DMX and Art-Net: kicks trigger the strobo, moving masks drift across your rig. A cross-platform (macOS / Windows) port of a vvvv gamma patch; it also drives PitchPlease LED strips.

Website, documentation and downloads: **[pitchcontrol.eu](https://pitchcontrol.eu)**.

Community: **[Discord](https://discord.gg/4nbBaQDKz4)** for questions and chat, [GitHub issues](https://github.com/hlavamir/PitchControl/issues) for bugs (Help → About → Report a problem fills one in), [Discussions → Ideas](https://github.com/hlavamir/PitchControl/discussions/categories/ideas) for feature ideas.

## Pages

Keys 1–9 switch between the pages; Connections and the Control Desk have a row of subpage tabs under the page row, and Q / E step through them. Everything can be operated from the keyboard (see [Using the UI](keyboard-and-mouse.md)). The footer at the bottom of every page shows the keys for the control under the mouse and a short explanation of it; the screenshots show it without a hovered control. On a first start the macros begin with their defaults: a calm test pattern for setting up the DMX output (Strobo and Audio Reactivity at 0, so the music changes nothing until you raise them).

1. [General](general.md): the page for playing the show: macros, functions and masks, scenes, the scene preview, the audio analysis
2. [Dimmers](dimmers.md): sixteen dimmer faders, one per group of lights
3. [Fixtures](fixtures.md): the fixture types and their channel modes
4. [Rig](rig.md): the fixtures of one event: addresses, groups, placement, per-fixture values
5. [Connections](connections.md): Audio, MIDI, DMX & Art-Net, USB DMX interfaces, OSC output, Serial
6. [Fog](fog.md): fog machines with a timer and a manual trigger
7. [Control Desk](control-desk.md): every DMX channel as a slider, overrides, and the routes from Art-Net, DMX or MIDI
8. [Settings](settings.md): appearance, network, engine frame rate, the log
9. [Help](help.md): keyboard reference, About, bug report, update check, support

## More

- [Keyboard and mouse](keyboard-and-mouse.md): the keys, the footer, the header's indicators, dialogs, navigating by keyboard
- [Other devices on the network](network.md): a phone or an iPad as a remote: switch, port, PIN, the phone layout
- [Folders](folders.md): defaults, your data and this computer's files; the file formats
- [Fixture library and imports](fixture-library.md): the ten shipped fixture types; importing from the Open Fixture Library and QLC+
- [Development and the standalone app](development.md): architecture, download, running from source, building the app, releasing a version
- [Status](status.md): what is tested and what has been verified on hardware

## License

MIT, see [LICENSE](../LICENSE).
