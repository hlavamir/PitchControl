"""PyInstaller entry point for the standalone PitchControl app."""

import sys

if __name__ == "__main__":
    if "--list-audio-devices" in sys.argv:
        # The app started by itself to list the audio devices (item 32): print them and exit, before anything of the app
        # (the window, the engine, uvicorn) is imported, so that nothing appears in the Dock or on screen.
        from pitchcontrol.io.audio_in import list_devices_main

        list_devices_main()
        sys.exit(0)
    from pitchcontrol.desktop import main

    main()
