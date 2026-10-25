"""Item 93: Learn tells what the hardware is (gate, trigger, latching, fader, encoder) and sets the row's mode from it."""

import mido
import pytest

from pitchcontrol.config.models import Controller, MidiMapping
from pitchcontrol.engine.macros import MacroBank
from pitchcontrol.io.learn_detect import Detection, classify, fill_for
from pitchcontrol.io.midi_in import LEARN_SECONDS, LEARN_WATCH, MidiInput

from test_midi import cc, clock, note  # noqa: F401  (clock is a fixture)


def at(*values, gap=0.05):
    return [(v, i * gap) for i, v in enumerate(values)]


# --------------------------------------------------------------------------- the classifier


@pytest.mark.parametrize("kind,press", [("cc", 127), ("note", 127), ("note", 90)])
def test_a_press_that_is_let_go_soon_is_a_gate_button(kind, press):
    assert classify(kind, [(press, 0.0), (0, 0.3)]).kind == "gate"
    assert classify(kind, [(press, 0.0), (0, 0.2), (press, 0.8), (0, 1.0)]).kind == "gate"


def test_a_press_let_go_only_much_later_is_the_second_press_of_a_latching_button():
    assert classify("cc", [(127, 0.0), (0, 2.5)]).kind == "latching"
    assert classify("note", [(100, 0.0), (0, 3.0)]).kind == "latching"


@pytest.mark.parametrize("kind", ["cc", "note"])
def test_presses_with_no_release_are_a_trigger_button(kind):
    assert classify(kind, [(127, 0.0), (127, 2.0)]).kind == "trigger"
    assert classify(kind, [(127, 0.0), (127, 2.0), (127, 4.0)]).kind == "trigger"


def test_a_note_with_other_velocities_is_still_a_press():
    assert classify("note", [(40, 0.0), (101, 2.0)]).kind == "trigger"


def test_a_single_press_asks_for_another_one():
    assert classify("cc", [(127, 0.0)]) == Detection("undecided", ask="press_again")
    assert classify("note", [(100, 0.0)]) == Detection("undecided", ask="press_again")


def test_a_control_that_sends_different_values_is_a_fader():
    assert classify("cc", at(10, 11, 12, 14, 20, 30)).kind == "fader"
    assert classify("cc", at(70, 80, 100, 127)).kind == "fader"  # all above 63 is no reason for a button
    assert classify("cc", at(3, 2, 1, 0)).kind == "fader"  # at the end of its travel
    assert classify("cc", at(125, 126, 127)).kind == "fader"  # a fader at the top, each value once, is not an encoder
    assert classify("cc", at(1, 2, 3)).kind == "fader"


def test_one_or_two_values_of_a_knob_ask_for_more_movement():
    assert classify("cc", at(64)) == Detection("undecided", ask="turn")
    assert classify("cc", at(50)) == Detection("undecided", ask="turn")
    assert classify("cc", at(50, 51)) == Detection("undecided", ask="turn")
    assert classify("cc", at(1)) == Detection("undecided", ask="turn")
    assert classify("cc", at(0)) == Detection("undecided", ask="turn")
    assert classify("cc", at(100, 90)) == Detection("undecided", ask="turn")  # two press values are no button


def test_two_s_complement_encoders_send_around_1_and_127():
    assert classify("cc", at(127, 127, 127, 127)) == Detection("encoder", "twos_complement")
    assert classify("cc", at(1, 1, 1)) == Detection("encoder", "twos_complement")
    assert classify("cc", at(1, 1, 2, 1)) == Detection("encoder", "twos_complement")  # accelerated
    assert classify("cc", at(127, 126, 127, 125)) == Detection("encoder", "twos_complement")
    assert classify("cc", at(1, 127, 1)) == Detection("encoder", "twos_complement")


def test_127_twice_slowly_is_a_trigger_button_and_in_a_burst_an_encoder():
    assert classify("cc", [(127, 0.0), (127, 1.8)]).kind == "trigger"
    assert classify("cc", [(127, 0.0), (127, 0.2)]) == Detection("encoder", "twos_complement")


def test_sign_bit_encoders_send_around_1_and_65():
    assert classify("cc", at(1, 65, 1, 65)) == Detection("encoder", "sign_bit")
    assert classify("cc", at(2, 66, 65, 1)) == Detection("encoder", "sign_bit")


def test_offset_64_encoders_send_around_63_and_65():
    assert classify("cc", at(63, 65, 63, 63)) == Detection("encoder", "offset_64")
    assert classify("cc", at(63, 63, 63)) == Detection("encoder", "offset_64")
    assert classify("cc", at(62, 63, 62)) == Detection("encoder", "offset_64")


def test_an_encoder_that_only_turned_up_65_could_be_sign_bit_or_offset_64_so_it_asks_for_the_other_way():
    assert classify("cc", at(65, 65, 66)) == Detection("undecided", ask="turn_other")


def test_one_encoder_value_is_not_enough_and_a_resting_value_is_no_encoder():
    assert classify("cc", at(63)).kind == "undecided"
    assert classify("cc", at(1)).ask == "turn"
    assert classify("cc", at(64)).ask == "turn"  # a knob at 64 is no encoder
    assert classify("cc", at(63, 64, 65)).kind == "fader"


def test_the_labels_say_what_it_is():
    assert Detection("gate").label == "gate button"
    assert Detection("encoder", "offset_64").label == "encoder (offset 64)"
    assert Detection("encoder", "twos_complement").label == "encoder (two's complement)"
    assert Detection("undecided", ask="turn").label == "unclear"


# --------------------------------------------------------------------------- the mode per macro kind


@pytest.mark.parametrize(
    "hardware,macro_kind,mode",
    [
        ("gate", "momentary", "momentary"),
        ("gate", "toggle", "toggle"),
        ("latching", "momentary", "momentary"),
        ("latching", "toggle", "momentary"),
        ("trigger", "toggle", "toggle"),
        ("trigger", "momentary", "trigger"),
        ("gate", "button", "trigger"),
        ("trigger", "radio", "trigger"),
    ],
)
def test_buttons_get_the_mode_that_fits_the_macro(hardware, macro_kind, mode):
    assert fill_for(Detection(hardware), macro_kind)[0] == mode


def test_a_trigger_on_a_hold_macro_says_it_cannot_be_held_and_a_latching_scene_button_says_it_fires_every_second_press():
    assert "can't be held" in fill_for(Detection("trigger"), "momentary")[2]
    assert "every second press" in fill_for(Detection("latching"), "button")[2]
    assert fill_for(Detection("gate"), "toggle")[2] == ""


def test_faders_and_encoders_on_a_value_macro():
    assert fill_for(Detection("fader"), "fader") == ("absolute", None, "")
    assert fill_for(Detection("encoder", "offset_64"), "fader") == ("relative", "offset_64", "")


@pytest.mark.parametrize(
    "hardware,macro_kind",
    [("gate", "fader"), ("trigger", "fader"), ("latching", "fader"), ("fader", "toggle"), ("encoder", "momentary"), ("fader", "button")],
)
def test_hardware_that_does_not_fit_the_macro_keeps_the_mode_and_says_so(hardware, macro_kind):
    mode, encoder, note_ = fill_for(Detection(hardware, "twos_complement" if hardware == "encoder" else None), macro_kind)
    assert mode is None and encoder is None and "mode kept" in note_


def test_an_undecided_control_and_an_unknown_macro_change_no_mode():
    assert fill_for(Detection("undecided", ask="turn"), "fader")[0] is None
    assert fill_for(Detection("gate"), None) == (None, None, "")


# --------------------------------------------------------------------------- Learn


def learner(macro, clock):
    midi = MidiInput(Controller(name="t", channel=1, mappings=[MidiMapping(number=100, macro="Strobo")]), MacroBank())
    midi.set_learning(True, macro=macro)
    return midi


def detected(midi):
    return midi.status()["learned"]["detected"]


def test_learn_watches_the_control_and_sets_a_gate_button_on_a_hold_macro_to_momentary(clock):
    midi = learner("Fog Machine", clock)
    cc(midi, 20, 127)
    clock.advance(0.3)
    cc(midi, 20, 0)
    assert midi.status()["learned"] is None and midi.status()["learning"]  # still watching
    clock.advance(LEARN_WATCH)
    learned = midi.status()["learned"]
    assert (learned["number"], learned["channel"]) == (20, 1)
    assert detected(midi) == {"kind": "gate", "label": "gate button", "mode": "momentary", "encoder": None, "note": ""}
    assert not midi.status()["learning"]


def test_the_same_gate_button_on_an_on_off_macro_is_a_toggle(clock):
    midi = learner("Swap Colors", clock)
    note(midi, 36, 100)
    note(midi, 36, 0)
    clock.advance(LEARN_WATCH + 0.1)
    assert detected(midi)["mode"] == "toggle" and midi.status()["learned"]["kind"] == "note"


def test_a_trigger_button_is_known_after_the_second_press(clock):
    midi = learner("Fog Machine", clock)
    cc(midi, 20, 127)
    clock.advance(LEARN_WATCH + 0.1)
    status = midi.status()
    assert status["learned"] is None and status["learning"] and status["learn_ask"] == "press_again"  # one press: asks
    clock.advance(3)
    cc(midi, 20, 127)
    status = midi.status()
    assert status["learned"] is not None and status["learn_ask"] is None
    assert detected(midi)["kind"] == "trigger" and detected(midi)["mode"] == "trigger" and "can't be held" in detected(midi)["note"]


def test_a_latching_button_is_known_by_its_second_press_sending_0(clock):
    midi = learner("Swap Colors", clock)
    cc(midi, 20, 127)
    clock.advance(LEARN_WATCH + 0.1)
    assert midi.status()["learn_ask"] == "press_again"
    clock.advance(2)
    cc(midi, 20, 0)
    assert detected(midi)["kind"] == "latching" and detected(midi)["mode"] == "momentary"  # the macro follows the button


def test_a_trigger_button_on_an_on_off_macro_is_a_toggle(clock):
    midi = learner("Swap Colors", clock)
    cc(midi, 20, 127)
    clock.advance(LEARN_WATCH + 0.1)
    clock.advance(2)
    cc(midi, 20, 127)
    assert detected(midi)["mode"] == "toggle"


def test_an_encoder_sets_relative_and_its_type_on_a_value_macro(clock):
    midi = learner("Hue A", clock)
    for value in (63, 63, 65, 63):
        cc(midi, 20, value)
        clock.advance(0.1)
    clock.advance(LEARN_WATCH)
    assert detected(midi)["mode"] == "relative" and detected(midi)["encoder"] == "offset_64"
    assert detected(midi)["label"] == "encoder (offset 64)"


def test_a_fader_sets_absolute_and_a_button_on_a_fader_macro_keeps_the_mode(clock):
    midi = learner("Hue A", clock)
    for value in (10, 20, 35, 50):
        cc(midi, 20, value)
        clock.advance(0.1)
    clock.advance(LEARN_WATCH)
    assert detected(midi)["mode"] == "absolute"
    midi = learner("Hue A", clock)
    cc(midi, 21, 127)
    cc(midi, 21, 0)
    clock.advance(LEARN_WATCH + 0.1)
    d = detected(midi)
    assert d["kind"] == "gate" and d["mode"] is None and "mode kept" in d["note"]


def test_a_knob_that_sent_one_value_asks_for_more_and_a_move_decides(clock):
    midi = learner("Hue A", clock)
    cc(midi, 20, 50)
    clock.advance(LEARN_WATCH + 0.1)
    assert midi.status()["learn_ask"] == "turn" and midi.status()["learned"] is None
    cc(midi, 20, 55)
    assert midi.status()["learned"] is None  # two values are still not enough
    cc(midi, 20, 70)
    assert detected(midi)["mode"] == "absolute"


def test_other_controls_are_ignored_while_learn_watches_but_still_shown_in_the_monitor(clock):
    midi = learner("Fog Machine", clock)
    cc(midi, 20, 127)
    cc(midi, 21, 127)  # another control: no part of the verdict
    cc(midi, 21, 0)
    cc(midi, 20, 0)
    clock.advance(LEARN_WATCH + 0.1)
    assert midi.status()["learned"]["number"] == 20 and detected(midi)["kind"] == "gate"
    assert [e["number"] for e in midi.recent] == [20, 21, 21, 20]
    cc(midi, 20, 127, channel=3)  # nor is the same number on another channel
    midi.set_learning(True, macro="Fog Machine")
    cc(midi, 20, 127)
    cc(midi, 20, 127, channel=3)
    cc(midi, 20, 0)
    clock.advance(LEARN_WATCH + 0.1)
    assert detected(midi)["kind"] == "gate"


def test_learn_times_out_while_asking_and_takes_the_control_with_its_mode_kept(clock):
    midi = learner("Fog Machine", clock)
    cc(midi, 20, 127)
    clock.advance(LEARN_WATCH + 0.1)
    assert midi.status()["learn_ask"] == "press_again"
    clock.advance(LEARN_SECONDS)
    learned = midi.status()["learned"]
    assert learned["number"] == 20 and learned["detected"]["kind"] == "undecided" and learned["detected"]["mode"] is None
    assert "couldn't tell" in learned["detected"]["note"]
    assert not midi.status()["learning"] or midi.status()["learn_ask"] is None


def test_learn_times_out_with_nothing_as_before(clock):
    midi = learner("Fog Machine", clock)
    clock.advance(LEARN_SECONDS + 1)
    assert midi.status()["learned"] is None and not midi.status()["learning"]


def test_cancelling_learn_forgets_the_watch(clock):
    midi = learner("Fog Machine", clock)
    cc(midi, 20, 127)
    assert midi.status()["learn_watching"]
    midi.set_learning(False)
    clock.advance(LEARN_WATCH + 1)
    assert midi.status()["learned"] is None and not midi.status()["learn_watching"] and midi.status()["learn_ask"] is None


def test_a_new_learn_does_not_inherit_the_watch_of_the_last_one(clock):
    midi = learner("Fog Machine", clock)
    cc(midi, 20, 127)
    midi.set_learning(True, macro="Fog Machine")
    clock.advance(LEARN_WATCH + 1)
    assert midi.status()["learned"] is None


def test_the_shift_row_takes_the_button_at_once_and_detects_nothing(clock):
    midi = MidiInput(Controller(name="t", channel=1, mappings=[]), MacroBank())
    midi.set_learning(True, [("cc", 60, 1)], for_shift=True, macro=None)
    cc(midi, 60, 127)
    learned = midi.status()["learned"]
    assert learned["number"] == 60 and "detected" not in learned


def test_a_row_without_a_known_macro_gets_the_control_only(clock):
    midi = learner("No Such Macro", clock)
    cc(midi, 20, 127)
    cc(midi, 20, 0)
    clock.advance(LEARN_WATCH + 0.1)
    assert detected(midi)["kind"] == "gate" and detected(midi)["mode"] is None


def test_mido_messages_for_a_note_off_count_as_a_release(clock):
    midi = learner("Swap Colors", clock)
    midi.handle(mido.Message("note_on", note=36, velocity=100))
    midi.handle(mido.Message("note_off", note=36, velocity=64))  # a note off's own velocity is no value
    clock.advance(LEARN_WATCH + 0.1)
    assert detected(midi)["kind"] == "gate"
