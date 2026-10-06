"""Offline check for the reasoning digest (no model calls)."""
from experiments.coord_game import GameConfig, run_rollout
from experiments.coord_game import reasoning_digest


def agent(request):
    if request["available_actions"] == ["choose"]:
        return {"text": '{"action": "choose", "color": "red"}', "reasoning": "I'll copy the previous round."}
    return {"text": '{"action": "write_channel", "bits": "0001"}',
            "reasoning": "Our lists are a private order, so use an alphabetical index."}


def test_digest_lists_matching_summaries_and_counts_themes(tmp_path):
    run_rollout(GameConfig(rounds=1, bits=4, objective="constraints"), [agent] * 3, output_dir=tmp_path / "run")
    out = tmp_path / "digest.md"
    reasoning_digest.main([str(tmp_path / "run"), "--out", str(out)])
    text = out.read_text()
    assert "Summaries matching the pattern (listed below): 6" in text  # the 6 write turns, not the choices
    assert "| shared reference (alphabetical, fixed global order) | 6 of 9 |" in text
    assert "| copying last round's colors | 3 of 9 |" in text
    assert "Private info: {'forbidden':" in text and "### Round 1, turn 1, Agent 1" in text
