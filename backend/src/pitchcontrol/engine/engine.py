"""The PitchControl engine: one frame = audio → phase → mask → fixtures → outputs.

Runs in its own thread at ``settings.fps`` (40 by default), independent of the
web UI. Everything that changes the engine from outside (API, MIDI) goes through
the thread-safe ``MacroBank`` or ``Engine.lock``.
"""

from __future__ import annotations

import copy
import logging
import threading
import time

import numpy as np

from ..config.loader import ConfigStore, load_model, save_model
from ..config.models import Scene
from ..io import audio_in
from ..io.audio_in import AudioInput
from ..io.midi_in import MidiInput, list_midi_inputs_checked
from ..io.outputs import OutputManager
from ..quitguard import UnsavedReports
from .audio_analysis import AudioFeatures, SpectrumAnalyzer, trigger_weights
from .colors import GroupColors, hsv_to_rgb
from .fixtures import Fixture, GroupBrightness
from .fog import FogController
from .macros import MacroBank
from .masks import PRESET_NAMES, MaskGenerator, MaskParams, PeaksMap, mixed_mask
from .overrides import Overrides
from .phase import PhaseTracker

log = logging.getLogger(__name__)

PREVIEW_SIZE = 256
AUDIO_WATCH_S = 2.0  # how often the audio input is looked at when it isn't on the saved device (item 30)
# The device list is read by starting a child process (0.3 s on the Mac, unmeasured on Windows). A cable stepped on is
# plugged back within seconds, so the first minute is looked at every AUDIO_WATCH_S; a device that has been away longer
# (the interface left at home, the stand-in running all night) is looked for every AUDIO_SLOW_WATCH_S only.
MIDI_WATCH_S = 2.0  # how often the MIDI input is looked at (listing the ports is cheap and cuts nothing: item 33)
AUDIO_FAST_PHASE_S = 60.0
AUDIO_SLOW_WATCH_S = 10.0
AUDIO_RETRY_S = 10.0  # after a reconnect that didn't work (the device is listed but won't open), wait this long


class MacroState(Scene):
    """``state/macros.json``: auto-saved macro values for crash recovery."""


class Engine:
    def __init__(self, store: ConfigStore, enable_hardware: bool = True):
        self.store = store
        self.enable_hardware = enable_hardware
        self.lock = threading.RLock()
        self.ui_unsaved = UnsavedReports()  # what the open pages say about their unsaved edits (asked when the desktop app quits)
        # stop → re-initialise PortAudio → start of the audio input, one at a time: two at once would terminate PortAudio
        # while the other thread opens its stream. Reentrant: the audio watchdog calls ``restart_audio``.
        self._audio_restart = threading.RLock()
        # item 30: what the audio watchdog saw. ``_audio_lost`` is the wall-clock time the input was lost (None: missing
        # since the start), ``_audio_back`` when it came back; both are kept for the Inputs page, in memory only.
        self._audio_problem: str | None = None  # "missing" | "dead" | "failed" while the saved device isn't running
        self._audio_lost: float | None = None
        self._audio_back: float | None = None
        self._audio_lost_device: str | None = None  # the device that was open when it dropped
        self._audio_back_device: str | None = None  # the device it runs on after (differs with no saved device)
        self._audio_link_device: str | None = None  # the saved device the two times above are about
        self._audio_retry_at = 0.0
        self._audio_problem_since = 0.0  # time.monotonic() the current problem was first seen
        self._audio_next_list = 0.0  # no device list before this time (monotonic)
        # item 33: the same for the MIDI input (what the watchdog saw, in memory only)
        self._midi_problem: str | None = None  # "lost" | "missing" | "failed" while the controller's port isn't open
        self._midi_lost: float | None = None
        self._midi_back: float | None = None
        self._midi_lost_port: str | None = None
        self._midi_back_port: str | None = None
        self._midi_link_key: str | None = None  # what is looked for (the port the two times are about)
        self._midi_restart = threading.Lock()  # one restart of the MIDI input at a time; closing and opening a port can be slow
        self.macros = MacroBank()
        self._restore_macros()
        self.overrides = Overrides()  # Control Desk: manual DMX channel values, saved across restarts
        self.overrides.load(self.store.state_dir / "overrides.json")
        self._overrides_saved = self.overrides.version

        self.phase = PhaseTracker()
        self.colors = GroupColors()
        self.fog = FogController()
        self.fixtures: list[Fixture] = []
        self.universes: dict[int, bytearray] = {}
        self.v2_strips: list[list[int]] = []

        grid = (np.arange(PREVIEW_SIZE) + 0.5) / PREVIEW_SIZE
        self.preview_u, self.preview_v = np.meshgrid(grid, grid)
        self._preview_inputs: tuple[MaskParams, bool] = (MaskParams(), False)

        self.outputs = OutputManager(store.settings.outputs, store.find_osc)
        self.audio: AudioInput | None = None
        self.midi: MidiInput | None = None

        self.frame = 0
        self.fps = 0.0
        self.tick_ms = 0.0
        self.peaks_total = 0
        self._last_save_version = self.macros.version
        self._last_save_time = time.monotonic()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        self.rebuild_audio_analysis()
        self.rebuild_masks()
        self.rebuild_fixtures()

    # ------------------------------------------------------------------ building
    def rebuild_audio_analysis(self) -> None:
        with self.lock:
            a = self.store.settings.audio
            self.analyzer = SpectrumAnalyzer(a)
            weights = trigger_weights(self.analyzer.layout.centres, a.trigger_full_hz, a.trigger_zero_hz)
            self.features = AudioFeatures(
                a.bands, weights, normalisation_decay=a.normalisation_decay, normalisation_floor=a.normalisation_floor
            )
            self.peaks = PeaksMap(a.bands)

    def rebuild_masks(self) -> None:
        with self.lock:
            m = self.store.settings.masks
            self.masks = MaskGenerator(transition_s=m.transition_s)

    def rebuild_fixtures(self) -> None:
        with self.lock:
            fixtures = []
            for inst in self.store.rig.fixtures:
                ftype = self.store.fixture_types.get(inst.type)
                if ftype is None or not inst.enabled:
                    continue
                fixtures.append(Fixture(inst, ftype))
            self.fixtures = fixtures
            sizes = [f.pixels for f in fixtures]
            self._offsets = np.concatenate(([0], np.cumsum(sizes))).astype(int)
            self._all_u = np.concatenate([f.uv[:, 0] for f in fixtures]) if fixtures else np.zeros(0)
            self._all_v = np.concatenate([f.uv[:, 1] for f in fixtures]) if fixtures else np.zeros(0)

    def start_io(self) -> None:
        if not self.enable_hardware:
            return
        s = self.store.settings
        self.outputs.restart(s.outputs)
        self.restart_audio()
        self.restart_midi()

    def restart_audio(self, reinit: bool = False) -> None:
        """Reopen the audio input from the saved settings. ``reinit`` makes PortAudio list the devices again first
        (with the old stream closed, which is why it cuts the input for a moment). It also does that by itself when a
        saved device isn't in this process's list: the Inputs page lists the devices as they are now (a child process),
        so a device plugged in after the start can be picked and saved before PortAudio here knows it."""
        with self._audio_restart:
            if self.audio is not None:
                self.audio.stop()
            self.audio = None
            if not self.enable_hardware:
                return
            a = self.store.settings.audio
            if reinit or (a.device and audio_in.match_device(a.device, audio_in.list_input_devices()) is None):
                audio_in.reinit_portaudio(a.device)
            self.rebuild_audio_analysis()
            self.audio = AudioInput(a.device, a.channels, a.sample_rate, lambda s: self.analyzer.push(s))
            self.audio.start()

    def audio_status(self) -> dict | None:
        """The audio input's status, with when the input was lost and came back (``reconnect``, null before any drop)."""
        audio = self.audio
        if audio is None:
            return None
        st = audio.status()
        link = {
            "lost": self._audio_lost,
            "back": self._audio_back,
            "lost_device": self._audio_lost_device,
            "back_device": self._audio_back_device,
        }
        st["reconnect"] = link if link["lost"] is not None or link["back"] is not None else None
        return st

    def audio_check(self) -> None:
        """One look of the audio watchdog (every ``AUDIO_WATCH_S``): when the input isn't running on the device the user
        saved (it was missing at the start, or its stream died), look at the real device list, which cuts nothing, and
        only when the saved device is listed re-initialise PortAudio and restart on it. Never switches to another
        device: with no device saved the system default is the user's choice, so a dead stream restarts on that.
        Log lines are written once per change, not every look. Called from the watchdog's own thread: the list blocks
        up to ``audio_in.LIST_TIMEOUT_S``, so never from the audio callback or the event loop."""
        if not self.enable_hardware:
            return
        # Read under the restart lock: a restart that runs right now (Save, Find new devices) has stopped the old input
        # and not yet opened the new one, which would look like a drop. The lock is held only during a restart.
        with self._audio_restart:
            audio, saved = self.audio, self.store.settings.audio.device
            st = audio.status() if audio is not None else None
        if audio is None or st is None:
            return
        if saved != self._audio_link_device:  # another device was saved: what happened to the old one is no longer news
            self._audio_lost = self._audio_back = None
            self._audio_lost_device = self._audio_back_device = None
            self._audio_problem = None
            self._audio_link_device = saved
        if st["running"] and not st["device_missing"]:
            if self._audio_problem is not None:
                self._audio_back, self._audio_back_device = time.time(), st["device"]
                log.info("audio input is back on '%s'", st["device"])
                self._audio_problem = None
            return
        problem = "dead" if st["dead"] else "missing" if st["device_missing"] else "failed"
        if self._audio_problem != problem:
            if self._audio_problem is None:  # a new drop, not a change of what is wrong with it
                self._audio_problem_since = time.monotonic()
                self._audio_next_list = 0.0
                self._audio_lost = audio.last_block_epoch() if problem == "dead" else None
                self._audio_lost_device = st["device"] if problem == "dead" else None
                self._audio_back = self._audio_back_device = None
            self._audio_problem = problem
            what = {
                "dead": f"audio input '{st['device']}' stopped delivering audio",
                "missing": f"saved audio device '{saved}' not found, listening to '{st['device']}'",
                "failed": f"audio input could not be opened: {st['error']}",
            }[problem]
            log.warning("%s; it reconnects by itself when the device is there", what)
        now = time.monotonic()
        if now < self._audio_retry_at or now < self._audio_next_list:
            return
        if saved and audio_in.match_device(saved, audio_in.list_input_devices_fresh()) is None:
            # still not plugged in: look again soon for a minute, then every few seconds only (see AUDIO_FAST_PHASE_S)
            away = time.monotonic() - self._audio_problem_since
            self._audio_next_list = time.monotonic() + (AUDIO_WATCH_S if away < AUDIO_FAST_PHASE_S else AUDIO_SLOW_WATCH_S)
            return
        with self._audio_restart:
            if self._stop.is_set() or self.audio is not audio or self.store.settings.audio.device != saved:
                return  # stopped, restarted by someone else or another device saved while the list was read
            cur = audio.status()
            if cur["running"] and not cur["device_missing"]:
                return  # it came back by itself while the list was read: no re-init cut for nothing
            log.info("audio input: %s again, restarting on it", f"'{saved}' is listed" if saved else "restarting")
            self.restart_audio(reinit=True)
            new = self.audio.status() if self.audio else None
            if new is None or not new["running"] or new["device_missing"]:
                self._audio_retry_at = time.monotonic() + AUDIO_RETRY_S
            else:
                self._audio_back, self._audio_back_device = time.time(), new["device"]
                self._audio_problem = None
                log.info("audio input is back on '%s'", new["device"])

    def _audio_watch(self) -> None:
        while not self._stop.wait(AUDIO_WATCH_S):
            try:
                self.audio_check()
            except Exception:  # noqa: BLE001 - the watchdog must outlive whatever one look runs into
                log.exception("audio watchdog")

    def restart_midi(self) -> None:
        # Restarts run one after the other (two at once would open the same, exclusive, port twice). The engine lock is
        # only held to swap ``self.midi``: closing and opening a port is up to the driver and must not stop the frames.
        with self._midi_restart:
            with self.lock:
                old, self.midi = self.midi, None
            if old is not None:
                old.stop()
            if not self.enable_hardware:
                return
            new = MidiInput(self.store.controller, self.store.settings.midi_input, self.macros, ignored=self.store.dimmer_unassigned)
            new.start()
            with self.lock:
                self.midi = new

    def midi_status(self, midi: MidiInput | None = None) -> dict | None:
        """The MIDI input's status, with when the port was lost and came back (``reconnect``, null before any drop)."""
        midi = midi or self.midi
        if midi is None:
            return None
        st = midi.status()
        if self._midi_lost is not None or self._midi_back is not None:
            st["reconnect"] = {
                "lost": self._midi_lost,
                "back": self._midi_back,
                "lost_device": self._midi_lost_port,
                "back_device": self._midi_back_port,
            }
        else:
            st["reconnect"] = None
        return st

    def midi_check(self) -> None:
        """One look of the MIDI watchdog (every ``MIDI_WATCH_S``): the input has no open port, or its port has gone from
        the system's list (a pulled cable: the open port object doesn't notice) → when the port is listed again, open it.
        Listing ports cuts nothing (item 27 on real CoreMIDI), so no re-init and nothing else is touched. A listing that
        fails is not a pulled controller: that look is skipped. Logs once per change."""
        if not self.enable_hardware:
            return
        with self._midi_restart:  # read under the restart lock: a restart in progress has no input yet, that's no drop
            midi = self.midi
        if midi is None or midi.controller is None:
            return
        key = midi.wanted_name()
        if key != self._midi_link_key:  # another port or controller was chosen: the old drop is no longer news
            self._midi_lost = self._midi_back = self._midi_lost_port = self._midi_back_port = None
            self._midi_problem = None
            self._midi_link_key = key
        names = list_midi_inputs_checked()
        if names is None:
            return
        listed = midi.find_port(names)
        if midi.port is not None:
            # Pulled only when nothing in the list matches the wanted name: Windows (WinMM) appends the port's index to
            # every name, so plugging in another device can renumber this one ("LCXL3 1 MIDI In 0" → "… 1"), and a
            # renamed match is the same controller, still open.
            if midi.port_name in names or listed is not None:
                if self._midi_problem is not None:
                    self._midi_problem = None
                return
            # pulled while open: close the dead port (this lets go of held buttons), and look for it again from there
            lost_port = midi.port_name
            log.warning("MIDI port '%s' is gone from the system's list; it reconnects by itself when plugged in", lost_port)
            self.restart_midi()
            self._midi_problem, self._midi_lost, self._midi_lost_port = "lost", time.time(), lost_port
            self._midi_back = self._midi_back_port = None
            return
        problem = "failed" if midi.error_kind == "open_failed" else "missing"
        if self._midi_problem is None:
            self._midi_problem = problem
            self._midi_lost, self._midi_lost_port = None, None  # missing since the start: no drop time
            self._midi_back = self._midi_back_port = None
        if listed is None:
            return  # still not plugged in
        with self._midi_restart:
            if self._stop.is_set() or self.midi is not midi:
                return  # stopped, or restarted by someone else (Save) while we looked
            midi.start()  # the same input object: only the port is opened again
            if midi.port is not None:
                self._midi_back, self._midi_back_port = time.time(), midi.port_name
                self._midi_problem = None
                log.info("MIDI input is back on '%s'", midi.port_name)

    def _midi_watch(self) -> None:
        while not self._stop.wait(MIDI_WATCH_S):
            try:
                self.midi_check()
            except Exception:  # noqa: BLE001 - the watchdog must outlive whatever one look runs into
                log.exception("MIDI watchdog")

    # ------------------------------------------------------------------ frame
    def tick(self, dt: float) -> None:
        t0 = time.perf_counter()
        with self.lock:
            m = self.macros
            s = self.store.settings
            self._handle_buttons()
            m.apply_settled(time.monotonic(), s.midi_settle_s)

            audio = self.audio
            if self.enable_hardware and (audio is None or not audio.delivering):
                # No input (dead, stopped or restarting): hold the look, not the signal (item 30, Miro). The analysis
                # isn't fed or read, the features keep their last values (bands, colours, masks stay as they were) and
                # nothing peaks, so no new strobo or peak trigger comes out of a frozen signal (a held last frame would:
                # the normalisation decays towards it and every band "peaks" over and over). MIDI and manual controls
                # work as always. What the analyser holds is dropped, so the music that comes back starts clean.
                self.analyzer.reset()
                self.features.hold()
            else:
                levels = self.analyzer.read_frame()
                self.features.update(levels)

            self.phase.update(
                dt,
                self.features.trigger_fraction,
                strobo_control=m.control("Strobo"),
                strobo_decay=m.value("Strobo Decay"),
                idle_attack=m.value("Idle Attack"),
                manual=m.on("Manual Strobo"),
            )
            on_peak = self.phase.on_peak
            if on_peak:
                self.peaks_total += 1

            params = MaskParams(
                preset=m.radio_index("preset"),
                shader_param=m.control("Mask Param B"),
                line_falloff=s.masks.line_falloff,
            )
            self.masks.update(dt, params.preset, m.value("Mask Param A"), params.shader_param, on_peak)
            self.peaks.update(self.features.peak, self.features.peak_score, m.control("Audio Reactivity"))
            self.colors.update(on_peak, m, s.auto_colors)
            symmetry = m.on("Vertical Symmetry")

            mask = mixed_mask(self.masks, self.peaks, self._all_u, self._all_v, params, symmetry)
            groups = {
                "A": GroupBrightness(
                    m.value("Strobo Brightness") * m.control("Strobo Bright. A"),
                    m.value("Idle Brightness") * m.control("Idle Bright. A"),
                ),
                "B": GroupBrightness(
                    m.value("Strobo Brightness") * m.control("Strobo Bright. B"),
                    m.value("Idle Brightness") * m.control("Idle Bright. B"),
                ),
            }
            universes: dict[int, bytearray] = {}
            v2_strips: list[list[int]] = []
            for i, fx in enumerate(self.fixtures):
                fx.update(mask[self._offsets[i] : self._offsets[i + 1]], self.phase.phase, self.colors, groups[fx.inst.group], m)
                if fx.ftype.transport == "pitchpls_v2":
                    fx.last_output = fx.pixel_bytes("RGB")
                    v2_strips.append(fx.last_output)
                    continue
                data = fx.dmx_bytes(m)
                fx.last_output = data
                uni = universes.setdefault(fx.inst.universe, bytearray(512))
                start = fx.inst.address - 1
                end = min(start + len(data), 512)
                uni[start:end] = bytes(data[: end - start])
            self.fog.update(dt, self.store.rig.fog_machines, m, universes)
            self.overrides.apply(universes)  # last: manual overrides win
            self.universes, self.v2_strips = universes, v2_strips

            self._preview_inputs = (params, symmetry)

        if self.enable_hardware:
            self.outputs.send(universes, v2_strips)
            if self.outputs.osc is not None:
                self.outputs.osc.send(self.base_colors())
        self._autosave_macros()
        self._autosave_overrides()
        self.frame += 1
        self.tick_ms = (time.perf_counter() - t0) * 1000.0

    def base_colors(self) -> dict[str, tuple[float, float, float]]:
        """The group colours A and B as RGB (floats 0..1), as the Hue / Saturation macros or Auto Color Change make
        them (Swap Colors applied): before strobo, brightness, masks, dimmers and gamma. What OSC sends."""
        out = {}
        for key, c in (("a", self.colors.a), ("b", self.colors.b)):
            r, g, b = hsv_to_rgb(np.array(c.h), np.array(c.s), np.array(c.b)).tolist()
            out[key] = (r, g, b)
        return out

    def _handle_buttons(self) -> None:
        for name in self.macros.take_buttons():
            parts = name.split()
            if len(parts) == 3 and parts[0] == "Scene" and parts[1].isdigit():
                index = int(parts[1]) - 1
                if parts[2] == "Save":
                    self.save_scene(index)
                elif parts[2] == "Load":
                    self.load_scene(index)

    # ------------------------------------------------------------------ scenes & persistence
    def save_scene(self, index: int, name: str | None = None) -> None:
        values = {k: v for k, v in self.macros.snapshot().items() if self.macros.defs[k].page not in ("scenes", "system")}
        old = self.store.load_scene(index)
        scene = Scene(name=name or (old.name if old and old.name else f"Scene {index + 1}"), values=values)
        self.store.save_scene(index, scene)
        log.info("saved scene %d", index + 1)

    def load_scene(self, index: int) -> bool:
        """Load a scene; an empty slot means the default values. True if the slot held a scene."""
        scene = self.store.load_scene(index)
        if scene is None:
            self.macros.reset_to_defaults()
            log.info("scene %d is empty: macros set to their defaults", index + 1)
            return False
        self.macros.load(scene.values, source=f"scene {index + 1}")
        log.info("loaded scene %d (%s)", index + 1, scene.name)
        return True

    def _restore_macros(self) -> None:
        """The values of the last session (the autosave), or on a first start the macro defaults."""
        path = self.store.state_dir / "macros.json"
        if path.exists():
            state = load_model(path, MacroState, broken=self.store.broken_file)
            if state is not None:
                self.macros.load(state.values, source=str(path))
                log.info("restored macro values from %s", path)
                return
        log.info("no saved macro values: started with the defaults")

    def _autosave_macros(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (self.macros.version == self._last_save_version or now - self._last_save_time < 5.0):
            return
        self._last_save_version = self.macros.version
        self._last_save_time = now
        try:
            save_model(self.store.state_dir / "macros.json", MacroState(name="autosave", values=self.macros.snapshot()))
        except OSError as exc:
            log.warning("macro autosave failed: %s", exc)

    def _autosave_overrides(self, force: bool = False) -> None:
        """Overrides are saved within a second of a change (they must survive a crash too)."""
        if self.overrides.version == self._overrides_saved:
            return
        if not force and self.frame % max(1, int(self.store.settings.fps)) != 0:
            return
        self._overrides_saved = self.overrides.version
        try:
            self.overrides.save(self.store.state_dir / "overrides.json")
        except OSError as exc:
            log.warning("override autosave failed: %s", exc)

    # ------------------------------------------------------------------ thread
    def start(self) -> None:
        self.start_io()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self._thread.start()
        if self.enable_hardware:
            threading.Thread(target=self._audio_watch, name="audio-watchdog", daemon=True).start()
            threading.Thread(target=self._midi_watch, name="midi-watchdog", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._autosave_macros(force=True)
        self._autosave_overrides(force=True)
        if self.audio is not None:
            self.audio.stop()
        if self.midi is not None:
            self.midi.stop()
        self.outputs.stop()

    def _run(self) -> None:
        period = 1.0 / max(self.store.settings.fps, 1.0)
        next_time = time.perf_counter()
        last = next_time
        fps_count, fps_time = 0, next_time
        while not self._stop.is_set():
            now = time.perf_counter()
            dt = min(now - last, 0.25)
            last = now
            try:
                self.tick(dt)
            except Exception:  # noqa: BLE001 - keep the show running, but log every failure
                log.exception("engine tick failed")
            fps_count += 1
            if now - fps_time >= 1.0:
                self.fps = fps_count / (now - fps_time)
                fps_count, fps_time = 0, now
            period = 1.0 / max(self.store.settings.fps, 1.0)
            next_time += period
            delay = next_time - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_time = time.perf_counter()  # running late: don't try to catch up

    # ------------------------------------------------------------------ state for the UI
    def render_preview(self) -> bytes:
        """256×256 grayscale image of the current scene.

        Copies the mask state under the lock and renders outside it, so the
        (up to ~20 ms) preview never delays the engine frame / DMX output.
        """
        with self.lock:
            masks = copy.deepcopy(self.masks)
            peaks = copy.deepcopy(self.peaks)
            params, symmetry = self._preview_inputs
        img = mixed_mask(masks, peaks, self.preview_u, self.preview_v, params, symmetry)
        return (np.clip(img, 0.0, 1.0) * 255).astype(np.uint8).tobytes()

    def state(self) -> dict:
        with self.lock:
            midi = self.midi  # read once
            fixtures = []
            for fx in self.fixtures:
                fixtures.append(
                    {
                        "name": fx.inst.name,
                        "type": fx.inst.type,
                        "group": fx.inst.group,
                        "transport": fx.ftype.transport,
                        "universe": fx.inst.universe,
                        "address": fx.inst.address,
                        "uv": np.round(fx.uv, 4).tolist(),
                        "rgb": (np.clip(fx.rgb, 0, 1) * 255).astype(int).tolist(),
                        "output": fx.last_output,
                    }
                )
            ca, cb = self.colors.a, self.colors.b
            rgb_a = hsv_to_rgb(np.array(ca.h), np.array(ca.s), np.array(ca.b)).tolist()
            rgb_b = hsv_to_rgb(np.array(cb.h), np.array(cb.s), np.array(cb.b)).tolist()
            return {
                "frame": self.frame,
                "fps": round(self.fps, 1),
                "tick_ms": round(self.tick_ms, 2),
                "macros": self.macros.snapshot(),
                "pending": self.macros.pending(),
                "phase": round(self.phase.phase, 4),
                "strobo": round(self.phase.strobo, 4),
                "idle": round(self.phase.idle, 4),
                "peaks_total": self.peaks_total,
                "trigger": round(self.features.trigger_fraction, 4),
                "bands": np.round(self.features.values, 3).tolist(),
                "band_peaks": self.features.peak.astype(int).tolist(),
                "peaks_map": np.round(self.peaks.blue, 3).tolist(),
                "preset": PRESET_NAMES[self.masks.current],
                "colors": {"A": rgb_a, "B": rgb_b},
                "colors_hsb": {"A": [ca.h, ca.s, ca.b], "B": [cb.h, cb.s, cb.b]},
                "fixtures": fixtures,
                "fog": self.fog.active,
                "overrides": self.overrides.snapshot(),
                "io": {
                    "outputs": self.outputs.status(),
                    "audio": self.audio_status(),
                    "midi": self.midi_status(midi),
                },
            }

    def universe_dump(self) -> dict[str, list[int]]:
        with self.lock:
            return {str(k): list(v) for k, v in self.universes.items()}


