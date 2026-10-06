"""Offline checks for the Docent export (no upload)."""
import pytest

from experiments.coord_game import GameConfig, run_rollout
from experiments.coord_game.docent import export_key, rollout_to_agent_run


def agent(request):
    if request["available_actions"] == ["choose"]:
        return {"text": '{"action": "choose", "color": "red"}', "reasoning": "pick red"}
    return {"text": '{"action": "write_channel", "bits": "1000"}', "reasoning": "send a signal"}


def broken_on_final(request):
    if request["available_actions"] == ["choose"]:
        raise ConnectionError("down")
    return agent(request)


@pytest.fixture
def rollout(tmp_path):
    return run_rollout(GameConfig(rounds=2, bits=4), [agent, agent, broken_on_final], output_dir=tmp_path / "run")


def test_one_transcript_per_agent_in_exact_history_order(rollout):
    run = rollout_to_agent_run(rollout)
    assert [t.name for t in run.transcripts] == ["Agent 1", "Agent 2", "Agent 3"]
    for transcript, history, system in zip(run.transcripts, rollout["agents"], rollout["system_prompts"]):
        texts = [m.content[-1].text for m in transcript.messages]
        assert texts == [system] + [m["content"] for m in history["messages"]]


def test_reasoning_is_attached_but_marked_not_replayed(rollout):
    first = rollout_to_agent_run(rollout).transcripts[0]
    answer = next(m for m in first.messages if m.role == "assistant")
    assert answer.content[0].reasoning == "send a signal"
    assert answer.metadata["reasoning_replayed_to_model"] is False
    assert (answer.metadata["round_index"], answer.metadata["turn_index"]) == (0, 0)


def test_run_metadata_and_stable_export_key(rollout):
    run = rollout_to_agent_run(rollout)
    assert run.metadata["export_key"] == export_key(rollout["rollout_id"]) == "coord-game-docent/v1:" + rollout["rollout_id"]
    assert run.metadata["summary"]["infrastructure_errors"] == 2
    assert run.metadata["rounds"][0]["choices"] == ["red", "red", None]
    assert "3 agents | broadcast | matching | feedback full | seed 0" in run.name
    assert run.metadata["tags"] == ["objective:matching", "feedback:full", "agents:3"]  # no effort tag here
    assert run.metadata["feedback"] == "full"


def test_mismatched_history_is_refused(rollout):
    rollout["agents"][1]["messages"][2]["content"] = "edited"  # an assistant message
    with pytest.raises(ValueError, match="Agent 2"):
        rollout_to_agent_run(rollout)


def test_unfinished_rollout_is_refused(rollout):
    rollout["status"] = "running"
    with pytest.raises(ValueError):
        rollout_to_agent_run(rollout)
