import logging
import math

import numpy as np
import pytest

from pitchcontrol.config.models import AudioSettings, FixtureInstance, IdleMaskRange, Rig
from pitchcontrol.engine.audio_analysis import AudioFeatures, SpectrumAnalyzer, make_layout, trigger_weights
from pitchcontrol.engine.colors import GroupColors
from pitchcontrol.engine.fixtures import Fixture, GroupBrightness, pixel_positions
from pitchcontrol.engine.macros import MacroBank, from_legacy_values, quantise
from pitchcontrol.engine.masks import MaskGenerator, MaskParams, PeaksMap, curved, mixed_mask, sample_linear_clamp
from pitchcontrol.engine.noise import noise_mask
from pitchcontrol.engine.phase import PhaseTracker


# ---------------------------------------------------------------- audio


def test_band_layout():
    layout = make_layout(AudioSettings())
    assert layout.count == 32
    assert layout.edges[0] == pytest.approx(35) and layout.edges[-1] == pytest.approx(10000)
    assert np.all(np.diff(layout.edges) >= 48000 / 2048 - 1e-9)  # every band ≥ one FFT bin
    assert np.all(layout.bin_hi > layout.bin_lo)


def test_trigger_weights_linear_over_octaves():
    w = trigger_weights(np.array([50, 100, 300, 1000, 5000, 8000.0]), 100, 5000)
    assert w[0] == 1 and w[1] == 1 and w[4] == 0 and w[5] == 0
    span = math.log2(50)
    assert w[2] == pytest.approx(1 - math.log2(3) / span)  # ≈ 0.72 at 300 Hz
    assert w[3] == pytest.approx(1 - math.log2(10) / span)  # ≈ 0.41 at 1 kHz


def test_kick_lands_in_low_bands():
    s = AudioSettings()
    an = SpectrumAnalyzer(s)
    t = np.arange(s.sample_rate // 4) / s.sample_rate
    an.push(0.5 * np.sin(2 * np.pi * 55 * t))  # 55 Hz "kick"
    levels = an.read_frame()
    assert levels.argmax() == np.searchsorted(an.layout.edges, 55) - 1
    assert levels[an.layout.centres > 1000].max() < 0.5 * levels.max()


def test_shared_normalisation_and_peaks():
    f = AudioFeatures(4, np.ones(4))
    f.update(np.array([0.9, 0.3, 0.3, 0.0]))
    assert f.values[0] == pytest.approx(1.0)  # the loudest band sets the scale for all of them ...
    assert f.values[1] == pytest.approx(1 / 3) and f.values[2] == pytest.approx(1 / 3)  # ... the others stay quieter
    assert f.values[3] == 0.0
    assert f.levels.tolist() == pytest.approx([0.9, 0.3, 0.3, 0.0])  # the bands before the division (item 75's display)
    assert f.peak[:3].all() and not f.peak[3]  # peaks are still found per band, against that band's own recent maximum
    assert f.trigger_fraction == pytest.approx(0.75)


def test_the_shared_maximum_decays_and_has_a_floor():
    f = AudioFeatures(2, np.ones(2), normalisation_decay=0.5, normalisation_floor=0.25)
    f.update(np.array([0.8, 0.1]))
    assert f.norm_max == pytest.approx(0.8)
    f.update(np.array([0.2, 0.1]))  # the loud band went quiet: the maximum follows down, by the decay
    assert f.norm_max == pytest.approx(0.4)
    assert f.values.tolist() == pytest.approx([0.5, 0.25])
    assert f.levels.tolist() == pytest.approx([0.2, 0.1])  # the live level is below the slowly decaying maximum
    for _ in range(10):
        f.update(np.array([0.0, 0.0]))
    assert f.norm_max == pytest.approx(0.25)  # never below the floor: silence isn't scaled up


# ---------------------------------------------------------------- macros & phase


def test_macro_range_and_quantise():
    m = MacroBank()
    m.set("Strobo Decay", 1.0)
    assert m.value("Strobo Decay") == pytest.approx(3.0)
    assert quantise(0.5, 2) == 1.0 and quantise(0.49, 2) == 0.0


def test_a_fader_is_continuous_and_a_toggle_still_snaps():
    m = MacroBank()
    m.set("Strobo Decay", 0.3003)  # between two of the old 128 steps (item 95)
    assert m.control("Strobo Decay") == 0.3003
    assert m.value("Strobo Decay") == pytest.approx(0.1 + 0.3003 * 2.9, abs=1e-12)
    m.set("Strobo", 1 / 127 / 3)
    assert m.value("Strobo") == pytest.approx(0.95 / 127 / 3, abs=1e-12)
    m.load({"Strobo Decay": 0.7007, "Mask Curve": 0.5})  # saved state and scenes hold control floats: the same positions
    assert m.control("Strobo Decay") == 0.7007 and m.value("Mask Curve") == pytest.approx(1.0)
    m.set("Swap Colors", 0.4)  # a toggle: below the middle is off, above is on
    assert m.value("Swap Colors") == 0.0
    m.set("Swap Colors", 0.6)
    assert m.value("Swap Colors") == 1.0


def test_radio_group():
    m = MacroBank()
    m.set("Mask C", 1)
    assert m.radio_index("preset") == 2 and not m.on("Mask A")


def test_legacy_values_mapping():
    values = [0.0] * 128
    values[5] = 0.8  # Glitches
    values[32] = 0.25  # Dimmer 01
    out = from_legacy_values(values)
    assert out["Audio Reactivity"] == 0.8 and out["Dimmer 01"] == 0.25


def test_phase_cycle():
    p = PhaseTracker()
    p.update(0.025, trigger_fraction=1.0, strobo_control=1.0, strobo_decay=1.0, idle_attack=2.0, manual=False)
    assert p.on_peak and p.phase == 0.0 and p.strobo == 1.0
    p.update(1.0, 0.0, 1.0, 1.0, 2.0, False)
    assert p.phase == pytest.approx(0.5) and p.strobo == 0.0 and p.idle == 0.0
    p.update(2.0, 0.0, 1.0, 1.0, 2.0, False)
    assert p.phase == pytest.approx(1.0)
    # minimum time between peaks: at Strobo = 1 it is 0.5 s
    p.update(0.1, 1.0, 1.0, 1.0, 2.0, False)
    assert p.on_peak
    p.update(0.1, 1.0, 1.0, 1.0, 2.0, False)
    assert not p.on_peak


# ---------------------------------------------------------------- fixtures


def _fixture(store, **kw):
    inst = FixtureInstance(name="t", type="rgb_panel", **kw)
    return Fixture(inst, store.fixture_types["rgb_panel"])


def test_strobo_fixture_shows_strobo_then_idle(store):
    colors, macros = GroupColors(), MacroBank()
    colors.update(False, macros, [])
    fx = _fixture(store, react_to_strobo=True)
    g = GroupBrightness(strobo=1.0, idle=1.0)
    fx.update(np.array([1.0]), 0.0, colors, g, macros)  # at the peak: full strobo (white)
    assert np.allclose(fx.rgb, 1.0)
    fx.update(np.array([1.0]), 0.5, colors, g, macros)  # strobo over, idle not started: black
    assert np.allclose(fx.rgb, 0.0)
    fx.update(np.array([1.0]), 1.0, colors, g, macros)  # idle: group colour
    assert fx.rgb.max() == pytest.approx(1.0)


def test_non_strobo_fixture_goes_dark_on_peak(store):
    colors, macros = GroupColors(), MacroBank()
    colors.update(False, macros, [])
    fx = _fixture(store, react_to_strobo=False)
    g = GroupBrightness(strobo=1.0, idle=1.0)
    fx.update(np.array([1.0]), 0.0, colors, g, macros)
    assert np.allclose(fx.rgb, 0.0)
    fx.update(np.array([1.0]), 0.25, colors, g, macros)
    assert fx.rgb.max() == pytest.approx(0.5)
    fx.update(np.array([1.0]), 0.5, colors, g, macros)
    assert fx.rgb.max() == pytest.approx(1.0)


def test_invert_discoball_range_only_with_macro(store):
    colors, macros = GroupColors(), MacroBank()
    colors.update(False, macros, [])
    fx = _fixture(store, idle_mask_range=IdleMaskRange(min=1.0, max=0.0, curve=0.0, macro="Invert Discoball"))
    g = GroupBrightness(1.0, 1.0)
    fx.update(np.array([1.0]), 1.0, colors, g, macros)
    assert fx.rgb.max() == pytest.approx(1.0)
    macros.set("Invert Discoball", 1.0)
    fx.update(np.array([1.0]), 1.0, colors, g, macros)
    assert fx.rgb.max() == pytest.approx(0.0)


def test_mask_curve_macro_is_logarithmic_with_one_in_the_middle():
    bank = MacroBank()
    assert bank.value("Mask Curve") == pytest.approx(2.2, abs=1e-9)  # the default, exactly (items 94, 95)
    bank.set("Mask Curve", 0.5)
    assert bank.value("Mask Curve") == pytest.approx(1.0)  # the middle of the travel
    bank.set("Mask Curve", 0.0)
    assert bank.value("Mask Curve") == pytest.approx(0.25)
    bank.set("Mask Curve", 1.0)
    assert bank.value("Mask Curve") == pytest.approx(4.0)
    bank.set("Mask Curve", 0.25)
    assert bank.value("Mask Curve") == pytest.approx(0.5)  # a quarter of the travel: half of 1
    bank.set("Mask Curve", 0.75)
    assert bank.value("Mask Curve") == pytest.approx(2.0)


def test_curved_mask_is_in_to_the_value():
    mask = np.array([0.0, 0.5, 1.0])
    assert curved(mask, 1.0).tolist() == pytest.approx([0.0, 0.5, 1.0])
    assert curved(mask, 4.0).tolist() == pytest.approx([0.0, 0.0625, 1.0])  # above 1: darker
    assert curved(mask, 0.25).tolist() == pytest.approx([0.0, 0.5**0.25, 1.0])  # below 1: brighter
    assert curved(np.array([1.5, -0.5]), 2.0).tolist() == pytest.approx([1.0, 0.0])  # a mask is 0..1


def test_the_macro_curve_comes_before_the_fixture_remap(store):
    colors, macros = GroupColors(), MacroBank()
    colors.update(False, macros, [])
    g = GroupBrightness(1.0, 1.0)
    fx = _fixture(store, idle_mask_range=IdleMaskRange(curve=1.0))  # the fixture's own curve: mask ** 2
    fx.update(np.array([0.5]), 1.0, colors, g, macros)
    assert fx.rgb.max() == pytest.approx(0.25)
    fx.update(curved(np.array([0.5]), 2.0), 1.0, colors, g, macros)  # the macro at 2: (0.5 ** 2) ** 2
    assert fx.rgb.max() == pytest.approx(0.5**4)


def test_the_curve_applies_while_the_fixture_remap_macro_is_off(store):
    colors, macros = GroupColors(), MacroBank()
    colors.update(False, macros, [])
    fx = _fixture(store, idle_mask_range=IdleMaskRange(min=1.0, max=0.0, curve=-3.0, macro="Invert Discoball"))
    fx.update(curved(np.array([0.5]), 2.0), 1.0, colors, GroupBrightness(1.0, 1.0), macros)
    assert fx.rgb.max() == pytest.approx(0.25)  # macro off: identity remap, only the macro's curve


def test_a_rigs_old_mask_curve_is_read_but_never_written():
    assert Rig().legacy_mask_curve is None  # a rig file without it
    rig = Rig.model_validate({"mask_curve": -1.5})
    assert rig.legacy_mask_curve == -1.5
    assert "mask_curve" not in rig.model_dump(mode="json", exclude_none=True) and "legacy_mask_curve" not in rig.model_dump()
    assert Rig.model_validate({"mask_curve": float("nan")}).legacy_mask_curve is None


def test_gamma_on_output_per_channel(store):
    colors, macros = GroupColors(), MacroBank()
    colors.update(False, macros, [])
    g = GroupBrightness(1.0, 1.0)
    # the colour stays perceptual (preview); the device curve is applied to the output bytes
    fx = _fixture(store, gamma=2.0, saturation_source="const", saturation=0.5)
    fx.update(np.array([1.0]), 1.0, colors, g, macros)
    assert fx.rgb.min() == pytest.approx(0.5)
    assert min(fx.pixel_bytes("RGB")) == round(0.25 * 255)  # per channel: 0.5 ** 2
    fx = _fixture(store, gamma=1.0, saturation_source="const", saturation=0.5)
    fx.update(np.array([1.0]), 1.0, colors, g, macros)
    assert min(fx.pixel_bytes("RGB")) == round(0.5 * 255)  # 1 = unchanged


def test_rgbw_white_taken_after_gamma(store):
    colors, macros = GroupColors(), MacroBank()
    colors.update(False, macros, [])
    fx = _fixture(store, gamma=2.0, saturation_source="const", saturation=0.0)  # white
    fx.update(np.array([0.5]), 1.0, colors, GroupBrightness(1.0, 1.0), macros)
    r, g_, b, w = fx.pixel_bytes("RGBW")
    assert (r, g_, b) == (0, 0, 0) and w == round(0.25 * 255)


def test_pixel_spread_vertical():
    inst = FixtureInstance(position=(0.5, 0.5), rotation=270, length=0.6)
    uv = pixel_positions(inst, 4)
    assert np.allclose(uv[:, 0], 0.5)
    assert uv[0, 1] == pytest.approx(0.725) and uv[-1, 1] == pytest.approx(0.275)


# ---------------------------------------------------------------- masks


def test_masks_are_in_range_and_crossfade():
    gen = MaskGenerator(transition_s=2.0)
    u, v = np.meshgrid(np.linspace(0, 1, 32), np.linspace(0, 1, 32))
    p = MaskParams()
    for preset in range(4):
        out = gen.evaluate_preset(preset, u, v, p)
        assert out.min() >= 0 and out.max() <= 1
    gen.update(0.0, 0, 0.0, 0.0, False)
    gen.update(1.0, 2, 0.0, 0.0, False)  # switch to preset 2 and advance half the transition
    assert gen.transition == pytest.approx(0.5)
    blended = gen.evaluate(u, v, p)
    expected = 0.5 * (gen.evaluate_preset(0, u, v, p) + gen.evaluate_preset(2, u, v, p))
    assert np.allclose(blended, expected)


def test_noise_is_deterministic_and_varied():
    u, v = np.meshgrid(np.linspace(0, 1, 64), np.linspace(0, 1, 64))
    a = noise_mask(u, v, time=3.0)
    assert np.array_equal(a, noise_mask(u, v, time=3.0))
    assert a.std() > 0.05


def test_audio_reactivity_zero_means_raw_mask():
    peaks = PeaksMap(32)
    peaks.update(np.ones(32, dtype=bool), np.ones(32), reactivity=0.0)
    mask = np.linspace(0, 1, 11)
    assert np.allclose(peaks.apply(mask), mask)
    peaks.update(np.ones(32, dtype=bool), np.ones(32), reactivity=1.0)
    assert peaks.control == pytest.approx(1.0)


def test_symmetry_mirrors_the_left_half_onto_the_right():
    gen = MaskGenerator()
    peaks = PeaksMap(32)
    p = MaskParams(preset=0, shader_param=1.0)  # horizontal gradient: f(u) = u
    u = np.array([0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0])
    v = np.full_like(u, 0.5)
    off = mixed_mask(gen, peaks, u, v, p, symmetry=False)
    assert np.allclose(off, u)  # without symmetry the image is as it is
    out = mixed_mask(gen, peaks, u, v, p, symmetry=True)
    # the left half is untouched, the right half is its mirror: no averaging of the two sides
    assert np.allclose(out, [0.0, 0.1, 0.25, 0.5, 0.25, 0.1, 0.0])


def test_texture_sampling():
    table = np.array([0.0, 1.0])
    assert sample_linear_clamp(table, np.array([0.0, 0.25, 0.5, 0.75, 1.0])).tolist() == [0.0, 0.0, 0.5, 1.0, 1.0]
