"""Offline checks for prompt structure. These check facts the text must carry, not its wording."""
import pytest

from experiments.coord_game import GameConfig, color_orders
from experiments.coord_game.channels import get_channel
from experiments.coord_game.config import FEEDBACK, IMPLEMENTED_CHANNELS, IMPLEMENTED_OBJECTIVES
from experiments.coord_game.prompts import (CHANNEL_PROMPTS, CHANNEL_VIEW_HEADINGS, OBJECTIVE_PROMPTS,
                                            WRITE_DESCRIPTIONS, action_result, label, round_message,
                                            round_report, system_prompt, turn_message)


CONFIG = GameConfig()  # N = 3, T = 3, B = 8


def test_agents_are_shown_one_based():
    assert [label(i) for i in range(3)] == ["Agent 1", "Agent 2", "Agent 3"]
    assert system_prompt(CONFIG, 0).startswith("You are Agent 1, one of 3 agents (Agent 1 to Agent 3)")


def test_system_prompt_states_the_rules():
    prompt = system_prompt(CONFIG, 1)
    for fact in ("exactly 8 characters", "5 rounds", "3 turns", "turns 1 to 2", "On turn 3",
                 "own private order", "1 - d/3", '"write_channel"', '"pass"', '"choose"'):
        assert fact in prompt
    single_turn = system_prompt(GameConfig(turns=1), 0)
    assert "single turn" in single_turn and '"write_channel"' not in single_turn


def test_round_message_restates_the_objective_and_lists_private_colors():
    colors = color_orders(CONFIG, 0)[2]
    message = round_message(CONFIG, 2, 0, colors)
    assert message.splitlines()[0] == "Round 1 of 5."
    assert OBJECTIVE_PROMPTS["matching"] in message
    assert str(list(colors)).replace("'", '"') in message  # this agent's own order


def test_turn_message_labels_senders_and_shows_empty_messages():
    channel = get_channel("broadcast", CONFIG)
    channel.stage(2, "00000001")
    channel.commit(0, 0)
    message = turn_message(CONFIG, 0, 1, channel.view(0))
    assert '- Agent 2: ""' in message and '- Agent 3: "00000001"' in message
    assert 'Your current message: ""' in message and "write_channel or pass" in message
    final = turn_message(CONFIG, 0, 2, channel.view(0))
    assert "the final turn" in final and "Choose your color" in final


def test_action_results():
    assert "Nothing was sent" in action_result(None, "bad bits", final_turn=False)
    assert "no color this round" in action_result(None, "unknown color", final_turn=True)
    assert action_result({"action": "write_channel", "bits": "01010101"}, None, False) == \
        "Your message was sent successfully."
    assert "red" in action_result({"action": "choose", "color": "red"}, None, True)


@pytest.mark.parametrize("feedback", FEEDBACK)
def test_round_report_follows_feedback_level(feedback):
    config = GameConfig(feedback=feedback)
    report = round_report(config, 1, 0, ["red", "red", None], {"edit_distance": 1, "score": 2 / 3})
    if feedback == "none":
        assert report is None
        return
    assert "0.67" in report
    assert ("Agent 2 (you): red" in report and "Agent 3: no color" in report) == (feedback == "full")


def test_every_implemented_option_has_text():
    assert set(IMPLEMENTED_OBJECTIVES) <= set(OBJECTIVE_PROMPTS)
    for name in IMPLEMENTED_CHANNELS:
        assert name in CHANNEL_PROMPTS and name in CHANNEL_VIEW_HEADINGS and name in WRITE_DESCRIPTIONS
