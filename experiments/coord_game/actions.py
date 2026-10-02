"""The action set, its tool schemas, and the two kinds of action check.

- Shape checks (parse_action): the response holds exactly one action with exactly
  its declared fields, all strings. Adapted from the color game's _parse_action.
- Rule checks (check_rules): the action is legal in this game, e.g. a message of
  exactly B bits, or a color from the list (in any capitalization).

An action is a dict such as {"action": "write_channel", "bits": "01100001"}.
"""
from __future__ import annotations

import copy
import json

from .channels import valid_message
from .prompts import CHOOSE_DESCRIPTION, FIELD_DESCRIPTIONS, PASS_DESCRIPTION, WRITE_DESCRIPTIONS

ACTIONS = ("write_channel", "pass", "choose")


def available_actions(config, turn_index):
    """Turns 1 to T - 1 are for writing or passing; the final turn is for choosing only."""
    if type(turn_index) is not int or not 0 <= turn_index < config.turns:
        raise ValueError("turn_index must be an integer in [0, turns)")
    return ["choose"] if turn_index == config.turns - 1 else ["write_channel", "pass"]


def action_fields(action, channel):
    """Each action's fields besides "action". write_channel's depend on the channel structure."""
    return {"write_channel": tuple(channel.write_fields), "pass": (), "choose": ("color",)}[action]


def tool_definitions(actions, config, channel):
    """One strict JSON-Schema function per action, in the provider-neutral shape
    the color game's model adapter wraps for each transport."""
    if not actions or len(set(actions)) != len(actions) or any(a not in ACTIONS for a in actions):
        raise ValueError("actions must contain distinct known actions")
    descriptions = {"write_channel": WRITE_DESCRIPTIONS[channel.name],
                    "pass": PASS_DESCRIPTION, "choose": CHOOSE_DESCRIPTION}
    tools = []
    for action in actions:
        fields = action_fields(action, channel)
        properties = {field: {"type": "string",
                              "description": FIELD_DESCRIPTIONS[field].format(bits=config.bits)}
                      for field in fields}
        tools.append({"name": action, "description": descriptions[action], "strict": True,
                      "parameters": {"type": "object", "additionalProperties": False,
                                     "properties": properties, "required": list(fields)}})
    return tools


def normalise_response(response):
    """Accept a full response dict, a bare string, or a bare action dict (for stubs and tests)."""
    if isinstance(response, str):
        return {"text": response}
    if not isinstance(response, dict):
        return {"text": "", "invalid_response_type": type(response).__name__}
    if isinstance(response.get("action"), str):
        return {"text": json.dumps(response), "action": copy.deepcopy(response)}
    return copy.deepcopy(response)


def parse_action(response, actions, channel):
    """Shape checks. Return the canonical action, or raise ValueError."""
    if response.get("response_tool_error") or response.get("tool_error"):
        raise ValueError("The response did not contain exactly one valid action call")
    finish = str(response.get("finish_reason") or "")
    if finish in ("length", "max_tokens") or finish.startswith("incomplete"):
        raise ValueError("The model response was truncated")
    action = response.get("action")
    if not isinstance(action, dict):
        text = response.get("text", "")
        if not isinstance(text, str):
            raise ValueError("Action text must be a string")
        try:
            action = json.loads(text)
        except ValueError as exc:
            raise ValueError("Return exactly one JSON action object") from exc
    if not isinstance(action, dict) or action.get("action") not in actions:
        raise ValueError(f"Action must be one of {list(actions)} on this turn")
    expected = {"action", *action_fields(action["action"], channel)}
    if set(action) != expected:
        raise ValueError(f"Fields for {action['action']} must be {sorted(expected)}")
    if any(not isinstance(action[field], str) for field in expected):
        raise ValueError("Every action field must be a string")
    return dict(action)


def check_rules(action, config):
    """Rule checks for an action that passed parse_action.

    Return the action with a chosen color in its listed spelling (capitalization
    is ignored), or raise ValueError if the action is illegal.
    """
    action = dict(action)
    if action["action"] == "write_channel" and not valid_message(action["bits"], config.bits):
        raise ValueError(f"A message must be exactly {config.bits} characters, each 0 or 1")
    if action["action"] == "choose":
        listed = {color.casefold(): color for color in config.colors}
        if action["color"].casefold() not in listed:
            raise ValueError("Choose a color from your list")
        action["color"] = listed[action["color"].casefold()]
    return action
