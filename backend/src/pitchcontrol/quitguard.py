"""Asking before the desktop app quits.

Quitting stops the engine, so the lights freeze on their last frame, and unsaved edits in the pages are lost.
``quit_reasons`` decides whether to ask (a plain function: no window needed to test it); ``confirm_quit`` shows
the question with the system's own dialog.

The question is not asked through pywebview: its ``closing`` handlers run on the window's UI thread, where pywebview's
confirmation dialog waits for that same thread (macOS) and the page can't be asked for its state (``evaluate_js``).
So the page reports its unsaved edits to the engine as they change (``Engine.ui_unsaved``), and the dialogs are the
operating system's: a message box on Windows, ``osascript`` on macOS.
"""

from __future__ import annotations

import logging
import subprocess
import sys

log = logging.getLogger(__name__)

TITLE = "Quit PitchControl?"


def live_outputs(outputs: dict | None) -> bool:
    """Whether any output is connected: an Enttec interface, Art-Net or PitchPls v2 (``Outputs.status()``)."""
    if not outputs:
        return False
    entries = [*(outputs.get("enttec") or []), outputs.get("artnet"), outputs.get("pitchpls_v2")]
    return any(isinstance(e, dict) and e.get("connected") for e in entries)


def quit_reasons(unsaved: list[str] | None, outputs: dict | None) -> list[str]:
    """Why quitting needs a question, one sentence each; empty: quit without asking.

    ``unsaved`` is the labels of the pages with unsaved edits, or None when that couldn't be found out (the page
    never reported, or reading failed): then ask anyway, as if there were unsaved edits."""
    reasons = []
    if live_outputs(outputs):
        reasons.append("The lights are live: quitting freezes the output on its last frame.")
    if unsaved is None:
        reasons.append("Unsaved changes: PitchControl couldn't check whether a page has edits that aren't saved.")
    elif unsaved:
        reasons.append(f"Unsaved changes on {', '.join(unsaved)}: quitting drops them.")
    return reasons


def confirm_quit(reasons: list[str]) -> bool:
    """Show the reasons and ask. True = quit. Whatever goes wrong with the dialog itself, the answer is True:
    the app must always be able to quit."""
    message = "\n\n".join(reasons) + "\n\nQuit anyway?"
    try:
        if sys.platform == "win32":
            import ctypes

            MB_OKCANCEL, MB_ICONWARNING, MB_SETFOREGROUND, MB_TOPMOST, IDOK = 0x1, 0x30, 0x10000, 0x40000, 1
            answer = ctypes.windll.user32.MessageBoxW(None, message, TITLE, MB_OKCANCEL | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST)
            return answer != 2  # IDCANCEL; 0 = the call failed
        if sys.platform == "darwin":
            script = [
                "on run argv",
                'display dialog (item 1 of argv) with title "' + TITLE + '" buttons {"Cancel", "Quit"} default button "Cancel" with icon caution',
                "end run",
            ]
            res = subprocess.run(["osascript", *sum((["-e", line] for line in script), []), message], capture_output=True, text=True)
            return not (res.returncode != 0 and "-128" in res.stderr)  # -128: Cancel was pressed
        log.warning("no quit dialog on %s: quitting without asking (%s)", sys.platform, "; ".join(reasons))
    except Exception:  # noqa: BLE001
        log.exception("the quit dialog failed: quitting")
    return True
