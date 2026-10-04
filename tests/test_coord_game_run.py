"""Offline checks for the paid-run script, using a stub models file (no API calls)."""
import json

import pytest

from experiments.coord_game import run


def models_file(tmp_path, **entry):
    script = [json.dumps({"action": "pass"})] * 2 + [json.dumps({"action": "choose", "color": "red"})]
    model = {"name": "fake", "transport": "stub", "model": "stub", "stub_texts": script, **entry}
    path = tmp_path / "models.yaml"
    path.write_text(json.dumps({"models": [model]}))  # JSON is valid YAML
    return path


def test_run_uses_the_effort_override_and_saves_a_transcript(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run, "REPO", tmp_path)
    run.main(["--model", "fake", "--models-file", str(models_file(tmp_path, effort="high")), "--seed", "7"])
    (output,) = (tmp_path / "reports" / "coord-game").iterdir()
    assert output.name.endswith("-fake-medium-full-seed7")
    saved = json.loads((output / "rollout.json").read_text())
    assert saved["models"][0]["effort"] == "medium" and saved["models"][0]["name"] == "fake@medium"
    assert saved["summary"]["mean_score"] == 1
    assert (output / "transcript.html").exists()
    assert "Round 5: choices=['red', 'red', 'red'] score=1.00" in capsys.readouterr().out


def test_feedback_flag_reaches_the_config(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "REPO", tmp_path)
    run.main(["--model", "fake", "--models-file", str(models_file(tmp_path)), "--feedback", "score_only"])
    (output,) = (tmp_path / "reports" / "coord-game").iterdir()
    assert output.name.endswith("-fake-medium-score_only-seed0")
    saved = json.loads((output / "rollout.json").read_text())
    assert saved["config"]["feedback"] == "score_only"
    report = [m["content"] for m in saved["agents"][0]["messages"] if m["content"].startswith("Round 1 results.")][0]
    assert "Final colors" not in report


def test_missing_key_stops_before_any_call(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "REPO", tmp_path)
    monkeypatch.delenv("COORD_TEST_KEY", raising=False)
    path = models_file(tmp_path, api_key_env="COORD_TEST_KEY")
    with pytest.raises(SystemExit, match="COORD_TEST_KEY is not set"):
        run.main(["--model", "fake", "--models-file", str(path)])
    assert not (tmp_path / "reports").exists()


def test_model_is_required():
    with pytest.raises(SystemExit):
        run.main([])
