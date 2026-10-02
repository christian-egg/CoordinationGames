"""Adapter from the shared model client to the coordination game's actions.

The game loop sends a request with the agent's system prompt, its history, and
the provider-neutral tools for this turn (actions.tool_definitions). ModelAgent:
1. wraps those tools in the transport's format and forces exactly one call,
2. calls ai_collusion.client.generate once (the client handles HTTP retries),
3. turns the single native call into canonical JSON text, e.g.
   '{"action": "write_channel", "bits": "01100001"}'.

Field-level checks are left to actions.parse_action, so there is one parser.
A response that isn't exactly one offered call gets response_tool_error, which
parse_action rejects. The provider's raw response is always kept.

Adapted from experiments/color_game/model.py, without the counter, realtime,
and tool_choice="auto" parts.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace

from ai_collusion.client import ModelConfig, generate

ADAPTER_VERSION = "coord-game-adapter-v1"
NATIVE_TRANSPORTS = ("openai", "responses")
TEXT_TRANSPORTS = ("stub",)  # the action arrives as JSON text, as described in the system prompt


def _wrap_tools(transport, tools):
    """Wrap provider-neutral tools, and force one call (named when only one tool is offered)."""
    if transport == "responses":
        wrapped = [{"type": "function", **tool} for tool in tools]
        choice = {"type": "function", "name": tools[0]["name"]} if len(tools) == 1 else "required"
    else:
        wrapped = [{"type": "function", "function": tool} for tool in tools]
        choice = ({"type": "function", "function": {"name": tools[0]["name"]}}
                  if len(tools) == 1 else "required")
    return {"tools": wrapped, "tool_choice": choice, "parallel_tool_calls": False}


def _native_calls(transport, raw):
    """The function calls in a raw provider response, as (name, arguments) pairs."""
    raw = raw if isinstance(raw, dict) else {}
    if transport == "responses":
        output = raw.get("output") if isinstance(raw.get("output"), list) else []
        return [(item.get("name"), item.get("arguments")) for item in output
                if isinstance(item, dict) and item.get("type") == "function_call"]
    choices = raw.get("choices") if isinstance(raw.get("choices"), list) else []
    message = choices[0].get("message") if len(choices) == 1 and isinstance(choices[0], dict) else None
    calls = message.get("tool_calls") if isinstance(message, dict) else None
    calls = calls if isinstance(calls, list) else []
    return [((c.get("function") or {}).get("name"), (c.get("function") or {}).get("arguments"))
            for c in calls if isinstance(c, dict) and c.get("type") == "function"]


def decode_native(transport, response, offered):
    """Turn exactly one offered native call into canonical action text."""
    response = dict(response)
    calls = _native_calls(transport, response.get("raw"))
    error, action = None, None
    try:
        if len(calls) != 1:
            raise ValueError(f"Expected exactly one action tool call; received {len(calls)}")
        name, arguments = calls[0]
        if name not in offered:
            raise ValueError(f"Tool {name!r} is not available on this turn")
        if not isinstance(arguments, str):
            raise ValueError(f"Tool {name!r} arguments must be a JSON string")
        arguments = json.loads(arguments)
        if not isinstance(arguments, dict) or "action" in arguments:
            raise ValueError(f"Tool {name!r} arguments must be an object of its declared fields")
        action = {"action": name, **arguments}
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        error = str(exc)
    response.update(text=json.dumps(action) if error is None else "",
                    text_source="native_tool_call" if error is None else "invalid_tool_call",
                    response_tool_error=error, tool_mode="native")
    return response


class ModelAgent:
    """One agent's model. Holds no game state: the loop sends the whole history every call."""

    def __init__(self, model: ModelConfig):
        if model.transport not in NATIVE_TRANSPORTS + TEXT_TRANSPORTS:
            raise NotImplementedError(
                f"transport {model.transport!r} is not supported by the coordination game yet "
                f"(supported: {NATIVE_TRANSPORTS + TEXT_TRANSPORTS})")
        self.model = model

    def metadata(self):
        # asdict(ModelConfig) has the API key's variable name, never its value.
        return {**asdict(self.model), "adapter": ADAPTER_VERSION,
                "action_interface": "native tool call" if self.model.transport in NATIVE_TRANSPORTS
                else "JSON text"}

    def _config_for(self, tools):
        if self.model.transport not in NATIVE_TRANSPORTS:
            return self.model
        extra = copy.deepcopy(self.model.extra_body)
        for key in ("tools", "tool_choice", "parallel_tool_calls", "response_format"):
            extra.pop(key, None)  # the game sets these, per turn
        extra.update(_wrap_tools(self.model.transport, tools))
        return replace(self.model, extra_body=extra, response_tool_name=None)

    def __call__(self, request):
        cfg = self._config_for(request["tools"])
        response = generate(cfg, request["system"], request["messages"],
                            temperature=cfg.temperature, seed=None)
        if cfg.transport in NATIVE_TRANSPORTS:
            response = decode_native(cfg.transport, response, request["available_actions"])
        return response
