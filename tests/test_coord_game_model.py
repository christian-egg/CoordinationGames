"""Offline checks for the model adapter. generate() is replaced, so no API calls are made."""
import json

import pytest

from ai_collusion.client import ModelConfig
from experiments.coord_game import GameConfig, run_rollout
from experiments.coord_game.actions import normalise_response, parse_action, tool_definitions
from experiments.coord_game.channels import get_channel
from experiments.coord_game.model import ModelAgent


CONFIG = GameConfig(bits=4)
CHANNEL = get_channel("broadcast", CONFIG)
WRITE_TURN = ["write_channel", "pass"]


def model(transport):
    return ModelConfig(name="test", transport=transport, model="test-model", api_key_env="OPENAI_API_KEY")


def request(actions):
    return {"system": "sys", "messages": [{"role": "user", "content": "Turn 1 of 3."}],
            "available_actions": actions, "tools": tool_definitions(actions, CONFIG, CHANNEL)}


def native(transport, *calls):
    """A saved response whose raw envelope holds these (name, arguments) calls."""
    if transport == "responses":
        raw = {"output": [{"type": "function_call", "name": n, "arguments": a} for n, a in calls]}
    else:
        raw = {"choices": [{"message": {"tool_calls": [
            {"type": "function", "function": {"name": n, "arguments": a}} for n, a in calls]}}]}
    return {"text": "", "finish_reason": "stop", "raw": raw, "usage": {"total_tokens": 9}}


def fake_generate(monkeypatch, response):
    seen = {}

    def generate(cfg, system, messages, **kwargs):
        seen.update(cfg=cfg, system=system, messages=messages)
        return response

    monkeypatch.setattr("experiments.coord_game.model.generate", generate)
    return seen


@pytest.mark.parametrize("transport", ["responses", "openai"])
def test_tools_are_wrapped_and_one_call_is_forced(monkeypatch, transport):
    seen = fake_generate(monkeypatch, native(transport, ("pass", "{}")))
    ModelAgent(model(transport))(request(WRITE_TURN))
    extra = seen["cfg"].extra_body
    assert extra["tool_choice"] == "required" and extra["parallel_tool_calls"] is False
    names = [t["name"] if transport == "responses" else t["function"]["name"] for t in extra["tools"]]
    assert names == WRITE_TURN
    ModelAgent(model(transport))(request(["choose"]))  # one tool: that tool is named
    assert "choose" in json.dumps(seen["cfg"].extra_body["tool_choice"])


@pytest.mark.parametrize("transport", ["responses", "openai"])
@pytest.mark.parametrize("call, actions, action", [
    (("write_channel", '{"bits": "0110"}'), WRITE_TURN, {"action": "write_channel", "bits": "0110"}),
    (("pass", "{}"), WRITE_TURN, {"action": "pass"}),
    (("choose", '{"color": "red"}'), ["choose"], {"action": "choose", "color": "red"}),
])
def test_one_native_call_becomes_a_parsed_action(monkeypatch, transport, call, actions, action):
    saved = native(transport, call)
    fake_generate(monkeypatch, saved)
    response = ModelAgent(model(transport))(request(actions))
    assert response["raw"] == saved["raw"]  # the provider envelope is kept
    assert parse_action(normalise_response(response), actions, CHANNEL) == action


@pytest.mark.parametrize("transport", ["responses", "openai"])
@pytest.mark.parametrize("calls", [
    (),                                                   # no call
    (("pass", "{}"), ("pass", "{}")),                     # two calls
    (("choose", '{"color": "red"}'),),                    # not offered on a write turn
    (("write_channel", "not json"),),
    (("write_channel", '["0110"]'),),
    (("write_channel", '{"action": "pass"}'),),           # cannot smuggle in another action
])
def test_bad_native_calls_are_rejected_not_repaired(monkeypatch, transport, calls):
    fake_generate(monkeypatch, native(transport, *calls))
    response = ModelAgent(model(transport))(request(WRITE_TURN))
    assert response["response_tool_error"] and response["text"] == ""
    with pytest.raises(ValueError):
        parse_action(normalise_response(response), WRITE_TURN, CHANNEL)


def test_unsupported_transport_is_refused():
    with pytest.raises(NotImplementedError, match="not supported"):
        ModelAgent(model("anthropic"))


def test_metadata_never_holds_the_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    assert "sk-secret-value" not in json.dumps(ModelAgent(model("responses")).metadata())


def test_stub_models_play_a_full_rollout(tmp_path):
    # The stub replies with JSON text, cycling by the number of assistant messages so far.
    script = [json.dumps({"action": "write_channel", "bits": "1000"}), json.dumps({"action": "pass"}),
              json.dumps({"action": "choose", "color": "Red"})]
    stub = ModelConfig(name="stub", transport="stub", model="stub", stub_texts=script)
    config = GameConfig(rounds=2, turns=3, bits=4)
    rollout = run_rollout(config, [ModelAgent(stub) for _ in range(3)], output_dir=tmp_path / "run")
    assert rollout["status"] == "complete"
    assert [r["choices"] for r in rollout["rounds"]] == [["red"] * 3] * 2
    assert rollout["summary"]["bits_sent"] == [8, 8, 8]
