"""Offline checks for the action set, tool schemas, and action parsing."""
import json

import pytest

from experiments.coord_game import GameConfig
from experiments.coord_game.actions import (available_actions, check_rules, normalise_response,
                                            parse_action, tool_definitions)
from experiments.coord_game.channels import get_channel


CONFIG = GameConfig(bits=4)  # T = 3
CHANNEL = get_channel("broadcast", CONFIG)
WRITE_TURN = ["write_channel", "pass"]


def parse(response, actions=WRITE_TURN):
    return parse_action(normalise_response(response), actions, CHANNEL)


def test_final_turn_is_for_choosing_only():
    assert [available_actions(CONFIG, t) for t in range(3)] == [WRITE_TURN, WRITE_TURN, ["choose"]]
    assert available_actions(GameConfig(turns=1), 0) == ["choose"]  # no-communication baseline
    with pytest.raises(ValueError):
        available_actions(CONFIG, 3)


def test_tool_definitions_are_strict_with_exact_fields():
    tools = {t["name"]: t for t in tool_definitions(WRITE_TURN + ["choose"], CONFIG, CHANNEL)}
    assert set(tools) == {"write_channel", "pass", "choose"}
    for tool in tools.values():
        assert tool["strict"] and tool["parameters"]["additionalProperties"] is False
        assert tool["parameters"]["required"] == list(tool["parameters"]["properties"])
    assert list(tools["write_channel"]["parameters"]["properties"]) == ["bits"]
    assert "exactly 4 characters" in tools["write_channel"]["parameters"]["properties"]["bits"]["description"]
    assert tools["pass"]["parameters"]["properties"] == {}
    assert list(tools["choose"]["parameters"]["properties"]) == ["color"]
    json.dumps(tools)  # serializable for the request
    with pytest.raises(ValueError):
        tool_definitions(["write_channel", "write_channel"], CONFIG, CHANNEL)


@pytest.mark.parametrize("response, action", [
    ({"action": "write_channel", "bits": "0101"}, {"action": "write_channel", "bits": "0101"}),
    ('{"action": "pass"}', {"action": "pass"}),  # JSON text, as non-native transports send it
    ({"text": '{"action": "pass"}', "finish_reason": "stop"}, {"action": "pass"}),
])
def test_valid_actions_parse(response, action):
    assert parse(response) == action


@pytest.mark.parametrize("response", [
    {"action": "choose", "color": "red"},                 # not offered on a write turn
    {"action": "write_channel"},                          # missing field
    {"action": "write_channel", "bits": "0101", "to": 2},  # extra field
    {"action": "write_channel", "bits": 101},             # not a string
    {"action": "pass", "bits": None},                     # null fields are not ignored
    "not json",
    "[]",
    {"text": '{"action": "pass"}', "finish_reason": "length"},  # truncated
    {"text": "", "response_tool_error": "two tool calls"},
    42,
])
def test_malformed_actions_are_rejected(response):
    with pytest.raises(ValueError):
        parse(response)


def test_rule_checks():
    write = {"action": "write_channel", "bits": "0110"}
    assert check_rules(write, CONFIG) == write
    assert check_rules({"action": "pass"}, CONFIG) == {"action": "pass"}
    for spelling in ("red", "Red", "RED"):  # any capitalization; the listed spelling is recorded
        assert check_rules({"action": "choose", "color": spelling}, CONFIG) == {"action": "choose", "color": "red"}
    for bad in ({"action": "write_channel", "bits": "011"}, {"action": "write_channel", "bits": "0120"},
                {"action": "choose", "color": " red"}, {"action": "choose", "color": "teal"}):
        with pytest.raises(ValueError):
            check_rules(bad, CONFIG)
