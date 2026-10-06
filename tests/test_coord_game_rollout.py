"""Offline end-to-end checks for the rollout loop, using scripted agents (no model calls)."""
import json

import pytest

from experiments.coord_game import GameConfig
from experiments.coord_game.game import load_rollout, run_rollout


CONFIG = GameConfig(rounds=2, turns=3, bits=4)  # N = 3


def scripted(plan):
    """An agent that replays plan[(round_index, turn_index)], defaulting to pass/choose red."""
    requests = []

    def agent(request):
        requests.append(request)
        key = (request["round_index"], request["turn_index"])
        default = {"action": "choose", "color": "red"} if request["available_actions"] == ["choose"] \
            else {"action": "pass"}
        return plan.get(key, default)

    agent.requests = requests
    return agent


def leader_and_followers():
    return [scripted({(0, 0): {"action": "write_channel", "bits": "1000"}}), scripted({}), scripted({})]


def test_full_rollout_scores_and_saves(tmp_path):
    agents = leader_and_followers()
    rollout = run_rollout(CONFIG, agents, output_dir=tmp_path / "run")
    assert rollout["status"] == "complete"
    assert [r["choices"] for r in rollout["rounds"]] == [["red"] * 3] * 2
    assert rollout["summary"]["mean_score"] == 1 and rollout["summary"]["objective_met"] == 2
    assert rollout["rounds"][0]["bits_sent"] == [4, 0, 0] and rollout["summary"]["bits_sent"] == [4, 0, 0]
    from experiments.coord_game.prompts import PROMPT_VERSION
    assert rollout["prompt_version"] == PROMPT_VERSION
    for name in ("rollout.json", "events.jsonl", "source/experiments/coord_game/game.py"):
        assert (tmp_path / "run" / name).exists()
    assert load_rollout(tmp_path / "run") == json.loads(json.dumps(rollout))


def test_turns_are_simultaneous(tmp_path):
    agents = leader_and_followers()
    run_rollout(CONFIG, agents, output_dir=tmp_path / "run")
    turn0, turn1 = agents[1].requests[0], agents[1].requests[1]
    # Agent 1's write on turn 1 is not visible to Agent 2 until turn 2.
    assert '- Agent 1: ""' in turn0["messages"][-1]["content"]
    assert '- Agent 1: "1000"' in turn1["messages"][-1]["content"]
    # Every agent's turn-1 view is the same snapshot (empty channels).
    rnd = load_rollout(tmp_path / "run")["rounds"][0]
    assert all(v["others"][0]["bits"] == "" for v in rnd["turns"][0]["views"])


def test_tools_follow_the_turn(tmp_path):
    agents = leader_and_followers()
    run_rollout(CONFIG, agents, output_dir=tmp_path / "run")
    names = [[t["name"] for t in r["tools"]] for r in agents[0].requests[:3]]
    assert names == [["write_channel", "pass"], ["write_channel", "pass"], ["choose"]]


def test_channels_reset_and_history_persists_across_rounds(tmp_path):
    agents = leader_and_followers()
    run_rollout(CONFIG, agents, output_dir=tmp_path / "run")
    round2_first = agents[1].requests[3]
    assert round2_first["round_index"] == 1
    assert '- Agent 1: ""' in round2_first["messages"][-1]["content"]  # channel emptied
    contents = [m["content"] for m in round2_first["messages"]]
    assert contents[0].startswith("Round 1 of 2.") and any(c.startswith("Round 2 of 2.") for c in contents)
    assert any(c.startswith("Round 1 results.") for c in contents)  # full feedback by default


def test_invalid_write_is_a_pass_and_invalid_choice_is_empty(tmp_path):
    agents = [scripted({(0, 0): {"action": "write_channel", "bits": "10"}}),
              scripted({(0, 2): {"action": "choose", "color": "teal"}}),
              scripted({(0, 2): {"action": "choose", "color": "RED"}})]
    rollout = run_rollout(CONFIG, agents, output_dir=tmp_path / "run")
    rnd = rollout["rounds"][0]
    assert rnd["bits_sent"] == [0, 0, 0]
    assert rnd["choices"] == ["red", None, "red"]  # "teal" is empty; "RED" counts as red
    assert rnd["result"] == {"edit_distance": 1, "score": pytest.approx(2 / 3)}
    assert rnd["valid_for_analysis"]  # model mistakes are data, not infrastructure errors
    assert rollout["summary"]["invalid_actions"] == 2
    reply = agents[0].requests[1]["messages"][-2]["content"]
    assert reply.startswith("Invalid action:") and "Nothing was sent" in reply


def test_api_error_marks_round_invalid(tmp_path):
    def broken(request):
        if request["round_index"] == 0 and request["turn_index"] == 2:
            raise ConnectionError("network down")
        return {"action": "pass"} if request["available_actions"] != ["choose"] else \
            {"action": "choose", "color": "red"}

    rollout = run_rollout(CONFIG, [broken, scripted({}), scripted({})], output_dir=tmp_path / "run")
    assert rollout["status"] == "complete_with_errors"
    assert not rollout["rounds"][0]["valid_for_analysis"] and rollout["rounds"][1]["valid_for_analysis"]
    assert rollout["rounds"][0]["choices"][0] is None
    assert rollout["summary"]["valid_mean_score"] == 1
    assert "network down" not in (tmp_path / "run" / "events.jsonl").read_text()  # no raw exception text


def test_no_report_when_feedback_is_none(tmp_path):
    agents = leader_and_followers()
    run_rollout(GameConfig(rounds=2, turns=3, bits=4, feedback="none"), agents, output_dir=tmp_path / "run")
    assert not any("results." in m["content"] for m in agents[0].requests[-1]["messages"])


def test_journal_records_events_in_order(tmp_path):
    run_rollout(GameConfig(rounds=1, turns=2, bits=4), leader_and_followers(), output_dir=tmp_path / "run")
    kinds = [json.loads(line)["kind"] for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()]
    per_action = ["request", "response", "action_result"]
    assert kinds == ["rollout_start", "round_start", *per_action * 6, "round_end", "rollout_end"]


def test_refuses_unbuilt_options_and_reused_directories(tmp_path):
    with pytest.raises(NotImplementedError):
        run_rollout(GameConfig(channel="peer_to_peer"), leader_and_followers(), output_dir=tmp_path / "p2p")
    assert not (tmp_path / "p2p").exists()  # nothing written before the check
    (tmp_path / "used").mkdir()
    (tmp_path / "used" / "old.txt").write_text("x")
    with pytest.raises(FileExistsError):
        run_rollout(CONFIG, leader_and_followers(), output_dir=tmp_path / "used")
    with pytest.raises(ValueError):
        run_rollout(CONFIG, leader_and_followers()[:2], output_dir=tmp_path / "two")


def test_round_colors_and_private_info_flow_through_the_loop(tmp_path, monkeypatch):
    """A stand-in objective with 3 colors and a private preference per agent."""
    from experiments.coord_game import config as config_module, objectives, prompts

    class Stand_in(objectives.Matching):
        name = "majority"

        def round_colors(self, config, round_index):
            return ("red", "blue", "green")

        def private_info(self, config, round_index):
            return [{"preference": "blue"}] * config.n_agents

    monkeypatch.setitem(objectives.REGISTRY, "majority", Stand_in)
    monkeypatch.setattr(config_module, "IMPLEMENTED_OBJECTIVES", ("matching", "majority"))
    monkeypatch.setitem(prompts.OBJECTIVE_PROMPTS, "majority", "Stand-in objective.")
    monkeypatch.setitem(prompts.PRIVATE_INFO_PROMPTS, "majority", "Your preference: {preference}.")
    agents = [scripted({(0, 2): {"action": "choose", "color": "Blue"}}),
              scripted({(0, 2): {"action": "choose", "color": "blue"}}),
              scripted({(0, 2): {"action": "choose", "color": "yellow"}})]  # not in this round's list
    rollout = run_rollout(GameConfig(rounds=1, bits=4, objective="majority"), agents, output_dir=tmp_path / "run")
    rnd = rollout["rounds"][0]
    assert rnd["colors"] == ["red", "blue", "green"]
    assert all(sorted(order) == sorted(rnd["colors"]) for order in rnd["color_orders"])
    assert rnd["private_info"] == [{"preference": "blue"}] * 3
    assert rnd["choices"] == ["blue", "blue", None]  # "yellow" is invalid this round
    opening = agents[0].requests[0]["messages"][0]["content"]
    assert "Your preference: blue." in opening and '"yellow"' not in opening


@pytest.mark.parametrize("objective", ["unique", "dichotomy", "majority", "constraints"])
def test_every_objective_runs_end_to_end(tmp_path, objective):
    """Scripted agents choose the first color of their own private list."""
    def first_color(request):
        if request["available_actions"] != ["choose"]:
            return {"action": "pass"}
        opening = [m["content"] for m in request["messages"] if m["content"].startswith("Round ")][-1]
        colors = json.loads(opening.split("Your colors this round: ")[1].splitlines()[0])
        return {"action": "choose", "color": colors[0]}

    config = GameConfig(rounds=2, bits=4, objective=objective)
    rollout = run_rollout(config, [first_color] * 3, output_dir=tmp_path / "run")
    assert rollout["status"] == "complete" and rollout["summary"]["invalid_actions"] == 0
    for rnd in rollout["rounds"]:
        assert all(c in rnd["colors"] for c in rnd["choices"])
        assert 0 <= rnd["result"]["score"] <= 1
    opening = rollout["agents"][0]["messages"][0]["content"]
    if objective in ("majority", "constraints"):
        assert "Your private" in opening
    if objective == "unique":
        assert len(rollout["rounds"][0]["colors"]) == 4


@pytest.mark.parametrize("carry", [True, False])
def test_reasoning_is_carried_only_to_the_same_agent(tmp_path, carry):
    details = lambda agent: [{"type": "reasoning.encrypted", "data": f"secret-of-agent-{agent}"}]

    def make(agent):
        def act(request):
            action = {"action": "choose", "color": "red"} if request["available_actions"] == ["choose"] \
                else {"action": "pass"}
            return {"text": json.dumps(action), "reasoning_details": details(agent)}
        act.requests = []
        return lambda request: (act.requests.append(request), act(request))[1]

    agents = [make(i) for i in range(3)]
    seen = []
    wrapped = [lambda r, a=a, i=i: (seen.append((i, r)), a(r))[1] for i, a in enumerate(agents)]
    rollout = run_rollout(GameConfig(rounds=1, bits=4, carry_reasoning=carry), wrapped, output_dir=tmp_path / "run")
    last_by_agent = {i: r for i, r in seen}
    for i, request in last_by_agent.items():
        carried = [m.get("reasoning_details") for m in request["messages"] if m["role"] == "assistant"]
        if carry:
            assert carried and all(c == details(i) for c in carried)  # its own, never another agent's
        else:
            assert all(c is None for c in carried)
    assert rollout["summary"]["reasoning_carried"] == (9 if carry else 0)
