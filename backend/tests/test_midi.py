import json
import time

import mido
import pytest

from pitchcontrol.config.models import Controller, MidiMapping
from pitchcontrol.engine.macros import MacroBank
from pitchcontrol.io.midi_in import MidiInput, decode_step, scale

from conftest import SHIPPED_CONFIG


def cc(midi, control, value, channel=0):
    midi.handle(mido.Message("control_change", channel=channel, control=control, value=value))


def note(midi, number, velocity=127, channel=0):
    midi.handle(mido.Message("note_on" if velocity else "note_off", channel=channel, note=number, velocity=velocity))


def build(*mappings, channel=1, **kw):
    ctrl = Controller(name="t", channel=channel, mappings=list(mappings), **kw)
    macros = MacroBank()
    return MidiInput(ctrl, None, macros), macros


def fader(number=5, macro="Strobo", **kw):
    return MidiMapping(number=number, macro=macro, **kw)


# --------------------------------------------------------------------------- basics


def test_mapped_cc_sets_macro():
    midi, macros = build(MidiMapping(cc=5, macro="Strobo"), channel=12)  # the pre-1.5 spelling: cc=
    cc(midi, 5, 64, channel=11)  # the first message only says where the fader is
    assert macros.control("Strobo") == 0.0
    cc(midi, 5, 127, channel=11)
    assert macros.control("Strobo") == 1.0
    assert midi.recent[-1]["macro"] == "Strobo"
    assert midi.recent[-1]["kind"] == "cc" and midi.recent[-1]["number"] == 5 and midi.recent[-1]["channel"] == 12


def test_toggle_flips_on_press_only():
    midi, macros = build(MidiMapping(number=6, macro="Swap Colors", mode="toggle"))
    cc(midi, 6, 127)
    cc(midi, 6, 0)
    assert macros.on("Swap Colors")
    cc(midi, 6, 127)
    assert not macros.on("Swap Colors")


def test_momentary_follows_the_button_and_invert_flips_it():
    midi, macros = build(MidiMapping(number=6, macro="Fog Machine", mode="momentary"), MidiMapping(number=7, macro="Manual Strobo", mode="momentary", invert=True))
    cc(midi, 6, 127)
    assert macros.on("Fog Machine")
    cc(midi, 6, 0)
    assert not macros.on("Fog Machine")
    cc(midi, 7, 0)
    assert macros.on("Manual Strobo")


def test_trigger_presses_a_button_macro_and_selects_a_radio():
    midi, macros = build(MidiMapping(number=40, macro="Scene 3 Load", mode="trigger"), MidiMapping(number=41, macro="Mask A", mode="trigger"))
    cc(midi, 40, 127)
    cc(midi, 40, 0)
    assert macros.take_buttons() == {"Scene 3 Load"}
    cc(midi, 41, 127)
    assert macros.on("Mask A") and not macros.on("Mask C")


def test_notes_work_like_buttons():
    midi, macros = build(MidiMapping(type="note", number=36, macro="Swap Colors", mode="toggle"), MidiMapping(type="note", number=37, macro="Fog Machine", mode="momentary"))
    note(midi, 36)
    note(midi, 36, 0)  # note off
    assert macros.on("Swap Colors")
    note(midi, 37)
    assert macros.on("Fog Machine")
    note(midi, 37, 0)
    assert not macros.on("Fog Machine")
    cc(midi, 36, 127)  # a CC with the same number is another control
    assert midi.recent[-1]["note"] == "CC 36 not mapped"


def test_wrong_channel_is_reported_not_applied():
    midi, macros = build(fader(), channel=12)
    cc(midi, 5, 127, channel=0)
    assert macros.control("Strobo") == 0.0
    assert "mapping expects 12" in midi.recent[-1]["note"]
    assert midi.status()["received"] == 1


def test_a_mapping_can_use_its_own_channel():
    midi, macros = build(MidiMapping(number=9, macro="Fog Machine", mode="momentary", channel=3), channel=1)
    cc(midi, 9, 127, channel=0)
    assert not macros.on("Fog Machine")
    cc(midi, 9, 127, channel=2)
    assert macros.on("Fog Machine")


# --------------------------------------------------------------------------- value scaling


def test_scale_function():
    assert scale(0.25, 0.25, 0.5) == 0.5
    assert scale(1.0, 0.25, 0.5) == 1.0
    assert scale(0.0, 0.25, 0.5) == 0.0
    assert scale(0.625, 0.25, 0.5) == pytest.approx(0.75)  # half way up: half way from 0.5 to 1
    assert scale(0.1, 1.0, 0.4) == pytest.approx(0.04)
    assert scale(1.0, 1.0, 0.4) == 0.4  # nowhere to go up


def test_fader_in_sync_follows_one_to_one():
    midi, macros = build(fader())
    macros.set("Strobo", 0.5)
    for v in (64, 80, 100, 20):
        cc(midi, 5, v)
        assert macros.control("Strobo") == pytest.approx(v / 127)


def test_fader_away_from_the_macro_scales_to_both_ends_together():
    midi, macros = build(fader())
    macros.set("Strobo", 0.5)
    cc(midi, 5, 32)  # hardware at 0.25, macro at 0.5: nothing moves
    assert macros.control("Strobo") == 0.5
    cc(midi, 5, 80)  # hardware 0.63 is half way up: the macro is half way from 0.5 to 1
    assert macros.control("Strobo") == pytest.approx(0.5 + (80 / 127 - 32 / 127) / (1 - 32 / 127) * 0.5)
    cc(midi, 5, 127)
    assert macros.control("Strobo") == 1.0
    cc(midi, 5, 100)  # arrived at the top: now 1:1
    assert macros.control("Strobo") == pytest.approx(100 / 127)


def test_scaling_is_continuous_when_the_direction_changes():
    midi, macros = build(fader())
    macros.set("Strobo", 0.8)
    cc(midi, 5, 20)
    values = []
    for v in (40, 60, 80, 60, 40, 20, 10, 0):
        cc(midi, 5, v)
        values.append(macros.control("Strobo"))
    assert values[0] < values[1] < values[2] and values[2] > values[3] > values[4]
    assert values[5] == pytest.approx(0.8)  # back at the first position: the macro is where it was
    assert values[-1] == 0.0


def test_a_macro_changed_elsewhere_starts_a_new_takeover():
    midi, macros = build(fader())
    macros.set("Strobo", 0.5)
    cc(midi, 5, 10)
    cc(midi, 5, 30)
    macros.set("Strobo", 0.9)  # the UI or a scene
    cc(midi, 5, 31)
    assert macros.control("Strobo") == pytest.approx(0.9)  # not pulled back to the old scaling


def test_page_change_starts_over():
    midi, macros = build(fader(29, "Strobo Decay", page="general"), fader(29, "Dimmer 01", page="dimmers"))
    macros.set("Strobo Decay", 100 / 127)
    cc(midi, 29, 100)
    cc(midi, 29, 110)
    assert macros.control("Strobo Decay") == pytest.approx(110 / 127)
    macros.set_control_page("dimmers")
    cc(midi, 29, 50)  # Dimmer 01 is at 1.0 and the fader at 0.39: it must not jump
    assert macros.control("Dimmer 01") == 1.0
    assert macros.control("Strobo Decay") == pytest.approx(110 / 127)


def test_colour_knob_applies_once_it_rests():
    midi, macros = build(MidiMapping(number=33, macro="Hue A"))
    macros.set("Hue A", 10 / 127)
    for v in (10, 40, 90):  # turning the knob (it starts where the macro is)
        cc(midi, 33, v)
    assert macros.control("Hue A") == pytest.approx(10 / 127)  # nothing applied while turning
    assert macros.pending()["Hue A"] == pytest.approx(90 / 127)
    macros.apply_settled(time.monotonic() + 1.0, settle_s=0.4)
    assert macros.control("Hue A") == pytest.approx(90 / 127) and macros.pending() == {}


# --------------------------------------------------------------------------- encoders


@pytest.mark.parametrize(
    "encoder, values, steps",
    [
        ("twos_complement", (1, 2, 63, 127, 126, 65), (1, 2, 63, -1, -2, -63)),
        ("sign_bit", (1, 63, 65, 66, 127), (1, 63, -1, -2, -63)),
        ("offset_64", (65, 66, 63, 62, 64), (1, 2, -1, -2, 0)),
    ],
)
def test_decode_step(encoder, values, steps):
    assert tuple(decode_step(v, encoder) for v in values) == steps


def test_relative_encoder_moves_the_value_by_steps():
    midi, macros = build(fader(14, "Mask Param A", mode="relative", sensitivity=2.0))
    macros.set("Mask Param A", 0.5)
    cc(midi, 14, 1)
    cc(midi, 14, 1)
    assert macros.control("Mask Param A") == pytest.approx(0.5 + 4 / 127)
    cc(midi, 14, 127)  # one step down (two's complement)
    assert macros.control("Mask Param A") == pytest.approx(0.5 + 2 / 127)
    for _ in range(100):
        cc(midi, 14, 100)  # a big step down, clamped at 0
    assert macros.control("Mask Param A") == 0.0


def test_relative_invert_and_offset_encoder():
    midi, macros = build(fader(14, "Mask Param A", mode="relative", encoder="offset_64", invert=True))
    macros.set("Mask Param A", 0.5)
    cc(midi, 14, 65)  # +1, inverted
    assert macros.control("Mask Param A") == pytest.approx(0.5 - 1 / 127)


# --------------------------------------------------------------------------- shift and pages


def shifted_controller():
    return build(
        MidiMapping(number=44, mode="shift"),
        MidiMapping(number=37, macro="Scene 1 Load", mode="trigger", shift="off"),
        MidiMapping(number=37, macro="Scene 1 Save", mode="trigger", shift="on"),
        fader(5, "Strobo"),  # no shift condition: works either way
    )


def test_shift_changes_what_a_button_does():
    midi, macros = shifted_controller()
    cc(midi, 37, 127)
    assert macros.take_buttons() == {"Scene 1 Load"}
    cc(midi, 44, 127)  # shift down
    assert midi.shift and midi.status()["shift"]
    cc(midi, 37, 127)
    assert macros.take_buttons() == {"Scene 1 Save"}
    cc(midi, 44, 0)  # shift up
    assert not midi.shift
    cc(midi, 37, 127)
    assert macros.take_buttons() == {"Scene 1 Load"}


def test_shift_can_be_a_note_and_several_buttons_hold_it():
    midi, _ = build(MidiMapping(type="note", number=60, mode="shift"), MidiMapping(number=44, mode="shift"))
    note(midi, 60)
    cc(midi, 44, 127)
    note(midi, 60, 0)
    assert midi.shift  # the other one is still down
    cc(midi, 44, 0)
    assert not midi.shift


def test_unshifted_fader_still_works_with_shift_held():
    midi, macros = shifted_controller()
    macros.set("Strobo", 0.5)
    cc(midi, 44, 127)
    cc(midi, 5, 64)
    cc(midi, 5, 100)
    assert macros.control("Strobo") == pytest.approx(100 / 127)


def test_shift_tap_doesnt_decouple_an_unshifted_fader():
    midi, macros = shifted_controller()
    macros.set("Strobo", 120 / 127)
    cc(midi, 5, 120)  # in sync
    cc(midi, 44, 127)  # shift tapped: the fader's mapping is the same in both layers
    cc(midi, 44, 0)
    cc(midi, 5, 112)
    assert macros.control("Strobo") == pytest.approx(112 / 127)  # still 1:1, not scaled
    cc(midi, 44, 127)
    cc(midi, 5, 96)
    assert macros.control("Strobo") == pytest.approx(96 / 127)


def test_a_fader_whose_mapping_changes_with_shift_starts_over_in_both_directions():
    midi, macros = build(
        MidiMapping(number=44, mode="shift"),
        fader(5, "Strobo", shift="off"),
        fader(5, "Strobo Decay", shift="on"),
    )
    macros.set("Strobo", 100 / 127)
    macros.set("Strobo Decay", 0.0)
    cc(midi, 5, 100)
    cc(midi, 44, 127)
    cc(midi, 5, 100)  # the fader stands at 0.79, Strobo Decay at 0: nothing moves
    assert macros.control("Strobo Decay") == 0.0 and macros.control("Strobo") == pytest.approx(100 / 127)
    cc(midi, 5, 127)
    assert macros.control("Strobo Decay") == 1.0
    cc(midi, 44, 0)
    cc(midi, 5, 50)  # back to Strobo, which is at 0.79: scaled again, no jump to 0.39
    assert macros.control("Strobo") == pytest.approx(100 / 127)


def test_a_fader_that_wins_on_its_own_in_both_layers_keeps_its_takeover_across_a_page_change():
    midi, macros = build(fader(5, "Strobo"), fader(29, "Strobo Decay", page="general"), fader(29, "Dimmer 01", page="dimmers"))
    macros.set("Strobo", 0.5)
    cc(midi, 5, 32)  # scaling started: the macro stays at 0.5
    macros.set_control_page("dimmers")
    cc(midi, 5, 80)  # the same mapping on the new page: the scaling goes on, it doesn't start from here
    assert macros.control("Strobo") == pytest.approx(0.5 + (80 / 127 - 32 / 127) / (1 - 32 / 127) * 0.5)


def test_a_mapping_for_the_page_beats_one_for_every_page():
    midi, macros = build(fader(29, "Strobo Decay"), fader(29, "Dimmer 01", page="dimmers"))
    macros.set("Strobo Decay", 0.0)
    macros.set("Dimmer 01", 0.0)
    cc(midi, 29, 0)
    cc(midi, 29, 127)
    assert macros.control("Strobo Decay") == 1.0
    macros.set_control_page("dimmers")
    macros.set("Dimmer 01", 0.0)
    cc(midi, 29, 0)
    cc(midi, 29, 127)
    assert macros.control("Dimmer 01") == 1.0


def test_same_control_drives_the_active_page():
    midi, macros = build(fader(29, "Strobo Decay", page="general"), fader(29, "Dimmer 01", page="dimmers"), channel=13)
    macros.set("Strobo Decay", 1.0)
    cc(midi, 29, 127, channel=12)
    cc(midi, 29, 127, channel=12)
    assert macros.control("Strobo Decay") == 1.0
    macros.set_control_page("dimmers")
    macros.set("Dimmer 01", 0.0)
    cc(midi, 29, 0, channel=12)
    cc(midi, 29, 0, channel=12)
    assert macros.control("Dimmer 01") == 0.0 and macros.control("Strobo Decay") == 1.0


def test_unmapped_on_this_page_is_reported():
    midi, macros = build(fader(29, "Dimmer 01", page="dimmers"))
    cc(midi, 29, 10)
    assert "not mapped on page 'general'" in midi.recent[-1]["note"]


# --------------------------------------------------------------------------- releases (Miles' notes, items 1 and 2)


def fog_and_preset():
    return build(
        MidiMapping(number=44, mode="shift"),
        MidiMapping(number=38, macro="Fog Machine", mode="momentary", shift="off"),
        MidiMapping(number=38, macro="Mask C", mode="trigger", shift="on"),
        MidiMapping(number=37, macro="Manual Strobo", mode="momentary", page="general"),
    )


def test_release_goes_to_the_mapping_that_got_the_press():
    midi, macros = fog_and_preset()
    cc(midi, 38, 127)  # fog on
    assert macros.on("Fog Machine")
    cc(midi, 44, 127)  # shift pressed while the fog button is down
    cc(midi, 38, 0)  # fog button released: it belongs to Fog Machine, not to Mask C
    assert not macros.on("Fog Machine")
    assert not macros.on("Mask C")
    cc(midi, 44, 0)
    assert not midi.shift


def test_a_momentary_button_held_across_a_page_change_is_released():
    midi, macros = fog_and_preset()
    cc(midi, 37, 127)
    assert macros.on("Manual Strobo")
    macros.set_control_page("dimmers")  # the mapping is for the General page only
    cc(midi, 37, 0)
    assert not macros.on("Manual Strobo")


def test_closing_the_input_lets_go_of_held_buttons():
    midi, macros = fog_and_preset()
    cc(midi, 38, 127)
    cc(midi, 44, 127)
    midi.stop()  # a save of the active controller restarts the input while the button is down
    assert not macros.on("Fog Machine") and not midi.shift


def test_shift_and_releases_still_count_while_learning():
    midi, macros = fog_and_preset()
    cc(midi, 38, 127)  # fog held
    cc(midi, 44, 127)  # shift held
    midi.set_learning(True)
    cc(midi, 44, 0)  # shift let go during Learn
    cc(midi, 38, 0)  # and the fog button
    midi.set_learning(False)
    assert not midi.shift
    assert not macros.on("Fog Machine")


def test_learning_still_mutes_new_presses():
    midi, macros = fog_and_preset()
    midi.set_learning(True)
    cc(midi, 38, 127)
    assert not macros.on("Fog Machine")
    cc(midi, 38, 0)  # the release of a press that was never applied changes nothing
    midi.set_learning(False)
    assert not macros.on("Fog Machine")


def test_monitor_entries_say_whether_shift_was_held():
    midi, _ = fog_and_preset()
    cc(midi, 37, 127)
    cc(midi, 44, 127)
    cc(midi, 37, 0)
    cc(midi, 40, 10)
    assert [e["shift"] for e in midi.recent] == [False, False, True, True]


def learnable(midi):
    return [(e["learnable"], e["release"], e["shift_button"]) for e in midi.recent]


def test_learn_picks_neither_shift_buttons_nor_releases():
    midi, _ = fog_and_preset()
    cc(midi, 44, 127)  # shift pressed
    cc(midi, 38, 127)  # a button
    cc(midi, 38, 0)  # let go of it
    cc(midi, 44, 0)  # let go of shift
    note(midi, 60)
    note(midi, 60, 0)
    assert learnable(midi) == [
        (False, False, True),  # shift press: the Shift row may take it, other rows not
        (True, False, False),
        (False, True, False),
        (False, True, True),
        (True, False, False),
        (False, True, False),
    ]


def test_a_fader_at_rest_is_learnable_but_a_button_held_from_before_is_not_when_released():
    midi, _ = fog_and_preset()
    cc(midi, 7, 0)  # a fader sitting at 0 that moves: learnable
    cc(midi, 7, 3)
    cc(midi, 9, 100)  # a control that went to 100 (button or fader) ...
    cc(midi, 9, 0)  # ... and back to 0: counts as a release
    cc(midi, 9, 5)  # moving again is learnable
    assert [e["learnable"] for e in midi.recent] == [True, True, True, False, True]


def test_a_macro_on_the_shift_button_never_fires_and_the_load_says_so(caplog):
    with caplog.at_level("WARNING", logger="pitchcontrol.io.midi_in"):
        midi, macros = build(MidiMapping(number=44, mode="shift"), MidiMapping(number=44, macro="Fog Machine", mode="momentary"), MidiMapping(number=44, macro="Strobo", channel=3))
    assert [r.message for r in caplog.records if "shift button" in r.message] == [
        "controller 't': cc 44 on channel 1 is the shift button, so 'Fog Machine' mapped to it never fires"
    ]  # the one on another channel is a different control
    cc(midi, 44, 127)
    assert not macros.on("Fog Machine") and midi.shift  # the reproduced case: the shift mapping wins


# --------------------------------------------------------------------------- learn mode


def test_status_names_the_port_override():
    midi, _ = build(MidiMapping(number=6, macro="Fog Machine", mode="momentary"))
    assert midi.status()["port_override"] is None
    midi.port_override = "APC40"
    assert midi.status()["port_override"] == "APC40"


def test_learning_shows_messages_without_applying_them():
    midi, macros = build(MidiMapping(number=6, macro="Fog Machine", mode="momentary"))
    midi.set_learning(True)
    assert midi.status()["learning"]
    cc(midi, 6, 127)
    assert not macros.on("Fog Machine")
    assert midi.recent[-1]["number"] == 6 and midi.recent[-1]["note"].startswith("learning")
    midi.set_learning(False)
    cc(midi, 6, 127)
    assert macros.on("Fog Machine")


def test_learn_captures_the_first_control_itself_and_ends():
    midi, macros = build(MidiMapping(number=6, macro="Fog Machine", mode="momentary"))
    learn_id = midi.set_learning(True)
    status = midi.status()
    assert status["learning"] and status["learn_id"] == learn_id and status["learned"] is None
    cc(midi, 20, 90)  # the first message is taken ...
    cc(midi, 21, 90, channel=4)  # ... not the newest
    status = midi.status()
    assert status["learned"] == {"id": learn_id, "kind": "cc", "number": 20, "channel": 1, "shift": False}
    assert not status["learning"]  # waiting is over
    cc(midi, 6, 127)  # the grace: the new control and whatever comes next is still muted until the UI has the result
    assert not macros.on("Fog Machine")
    midi.set_learning(False)
    cc(midi, 6, 127)
    assert macros.on("Fog Machine")


def test_learn_ends_by_itself(monkeypatch):
    import pitchcontrol.io.midi_in as module

    midi, macros = build(MidiMapping(number=6, macro="Fog Machine", mode="momentary"))
    monkeypatch.setattr(module, "LEARN_SECONDS", 0.05)
    midi.set_learning(True)
    time.sleep(0.1)
    assert not midi.status()["learning"] and midi.status()["learned"] is None
    cc(midi, 6, 127)  # nothing is captured after the timeout, and the press works again
    assert midi.status()["learned"] is None and macros.on("Fog Machine")


def test_every_learn_has_its_own_id_and_forgets_the_last_result():
    midi, _ = build(MidiMapping(number=6, macro="Fog Machine", mode="momentary"))
    first = midi.set_learning(True)
    cc(midi, 20, 90)
    other, _ = build(MidiMapping(number=6, macro="Fog Machine", mode="momentary"))
    second = other.set_learning(True)  # ids don't repeat across inputs (a restart makes a new one)
    assert second != first
    third = midi.set_learning(True)
    assert third != first and midi.status()["learned"] is None
    midi.set_learning(False)
    assert midi.status()["learned"] is None and not midi.status()["learning"] and midi.status()["learn_id"] == third


def test_learn_skips_releases_and_the_shift_buttons_of_the_draft():
    midi, _ = build(MidiMapping(number=44, mode="shift"))  # the saved shift button is CC 44
    cc(midi, 9, 100)  # a button held from before Learn
    draft_shift = [("cc", 60, 1)]  # the draft has another shift button, not saved yet
    midi.set_learning(True, draft_shift)
    cc(midi, 9, 0)  # its release
    cc(midi, 60, 127)  # the draft's shift button
    assert midi.status()["learned"] is None
    cc(midi, 45, 127)  # a real control, with the draft's shift held
    assert midi.status()["learned"]["number"] == 45 and midi.status()["learned"]["shift"] is True


def test_learn_order_click_then_shift_then_button_gives_with_shift_for_an_unsaved_shift_button():
    midi, _ = build()  # an empty draft: nothing is saved
    midi.set_learning(True, [("cc", 60, 1)])
    cc(midi, 60, 127)
    cc(midi, 45, 127)
    assert midi.status()["learned"] == {"id": midi.learn_id, "kind": "cc", "number": 45, "channel": 1, "shift": True}


def test_shift_held_before_learn_and_let_go_before_the_press_is_not_with_shift():
    midi, _ = build()
    cc(midi, 60, 127)  # held from before Learn
    midi.set_learning(True, [("cc", 60, 1)])
    cc(midi, 60, 0)
    cc(midi, 45, 127)
    assert midi.status()["learned"]["shift"] is False


def test_the_shift_row_learns_a_shift_button_without_with_shift():
    midi, _ = build()
    midi.set_learning(True, [("cc", 60, 1)], for_shift=True)
    cc(midi, 60, 127)
    assert midi.status()["learned"] == {"id": midi.learn_id, "kind": "cc", "number": 60, "channel": 1, "shift": False}


def test_learn_captures_notes_and_the_channel():
    midi, _ = build()
    midi.set_learning(True)
    note(midi, 36, 100, channel=9)
    assert midi.status()["learned"] == {"id": midi.learn_id, "kind": "note", "number": 36, "channel": 10, "shift": False}


# --------------------------------------------------------------------------- files


def test_old_files_load_into_the_flat_list():
    ctrl = Controller.model_validate(
        {
            "name": "old",
            "channel": 13,
            "mappings": [{"cc": 1, "macro": "Strobo"}],
            "pages": {"general": [{"cc": 29, "macro": "Strobo Decay"}], "dimmers": [{"cc": 29, "macro": "Dimmer 01", "mode": "absolute"}]},
            "page_knob": 13,
        }
    )
    got = [(m.number, m.macro, m.mode, m.page) for m in ctrl.mappings]
    # the knob that switched pages is gone: pages are switched with the Page macros now
    assert got == [(1, "Strobo", "absolute", None), (29, "Strobo Decay", "absolute", "general"), (29, "Dimmer 01", "absolute", "dimmers")]
    assert "pages" not in ctrl.model_dump() and "page_knob" not in ctrl.model_dump()
    assert Controller.model_validate({"mappings": [{"number": 13, "mode": "page_knob"}, {"number": 1, "macro": "Strobo"}]}).mappings[0].number == 1


def test_a_mapping_needs_a_macro_unless_it_is_a_modifier():
    with pytest.raises(ValueError):
        MidiMapping(number=3)
    assert MidiMapping(number=3, mode="shift").macro is None


def test_shipped_lcxl3_mapping_matches_ui_layout(store):
    ctrl = store.controller
    general = [m for m in ctrl.mappings if m.page == "general"]
    dimmers = [m for m in ctrl.mappings if m.page == "dimmers"]
    assert general[5].macro == "Saturation A"
    assert dimmers[8].number == 5 and dimmers[8].macro == "Dimmer 09"


def test_shipped_controllers_have_no_redundant_channels():
    # a mapping that repeats the controller's channel doesn't follow it when the channel is changed in the app
    for path in sorted((SHIPPED_CONFIG / "controllers").glob("*.json")):
        ctrl = Controller.model_validate(json.loads(path.read_text(encoding="utf-8")))
        redundant = [m.number for m in ctrl.mappings if m.channel == ctrl.channel]
        assert redundant == [], f"{path.name}: mappings with the controller's own channel {ctrl.channel}: {redundant}"


@pytest.mark.parametrize("reverse", [False, True])
def test_shift_beats_page_whatever_the_order_in_the_file(reverse):
    page_only = MidiMapping(number=5, macro="Manual Strobo", mode="momentary", page="general")
    shift_only = MidiMapping(number=5, macro="Fog Machine", mode="momentary", shift="on")
    both = MidiMapping(number=6, macro="Fog Machine", mode="momentary", page="general", shift="on")
    only_page = MidiMapping(number=6, macro="Manual Strobo", mode="momentary", page="general")
    order = [page_only, shift_only, both, only_page]
    midi, macros = build(*(order[::-1] if reverse else order), MidiMapping(number=44, mode="shift"))
    cc(midi, 5, 127)  # no shift: only the page mapping fits
    assert macros.on("Manual Strobo") and not macros.on("Fog Machine")
    cc(midi, 5, 0)
    cc(midi, 44, 127)  # shift held: both fit, the shift mapping wins over the page mapping
    cc(midi, 5, 127)
    assert macros.on("Fog Machine") and not macros.on("Manual Strobo")
    cc(midi, 5, 0)
    cc(midi, 6, 127)  # shift and page beats page only
    assert macros.on("Fog Machine") and not macros.on("Manual Strobo")
