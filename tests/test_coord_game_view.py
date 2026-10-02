"""Offline checks for the transcript view."""
from experiments.coord_game import GameConfig, run_rollout
from experiments.coord_game.view import render_rollout, save_html


def agent(script):
    def act(request):
        if request["available_actions"] == ["choose"]:
            return {"action": "choose", "color": "red"}
        return script.get((request["round_index"], request["turn_index"]), {"action": "pass"})
    return act


def test_transcript_shows_rounds_turns_and_agents(tmp_path):
    agents = [agent({(0, 0): {"action": "write_channel", "bits": "1000"}}), agent({}),
              agent({(0, 1): {"action": "write_channel", "bits": "1"}})]
    rollout = run_rollout(GameConfig(rounds=1, bits=4), agents, output_dir=tmp_path / "run")
    page = save_html(rollout, tmp_path / "run" / "transcript.html").read_text()
    assert page.startswith("<!doctype html>")
    for text in ("Mean score: 1.00", "Agent 1", "Agent 3", "Turn 3 of 3 (final)",
                 "write <code>1000</code>", "action error", "Final private histories",
                 'Agent 1: <code>&quot;1000&quot;</code> (4 bits)', "Agent 2: none (0 bits)"):
        assert text in page


def test_model_text_cannot_inject_html(tmp_path):
    def hostile(request):
        return "<script>alert(1)</script>"  # unparseable, saved as the response text

    rollout = run_rollout(GameConfig(rounds=1, bits=4), [hostile] * 3, output_dir=tmp_path / "run")
    page = render_rollout(rollout)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_fragment_for_notebooks(tmp_path):
    rollout = run_rollout(GameConfig(rounds=1, bits=4), [agent({})] * 3, output_dir=tmp_path / "run")
    fragment = render_rollout(rollout, full_document=False)
    assert fragment.startswith("<style>") and "<html" not in fragment
