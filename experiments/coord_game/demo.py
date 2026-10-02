"""Offline demo: one rollout with scripted stub models. No API calls, no key needed.

    uv run python -m experiments.coord_game.demo

The scripts are fixed in advance: Agent 1 sends a message and everyone chooses
red, so this checks the loop, prompts, files, and transcript. It is not evidence
that models formed a convention. Agent 3 sends a malformed message in round 2 so
the transcript shows how an invalid action looks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ai_collusion.client import ModelConfig

from .config import GameConfig
from .game import run_rollout
from .model import ModelAgent
from .view import save_html

REPO = Path(__file__).resolve().parents[2]


def _script(*actions):
    return [json.dumps(a) for a in actions]


WRITE = {"action": "write_channel", "bits": "10000000"}
PASS = {"action": "pass"}
RED = {"action": "choose", "color": "red"}
# The stub replies with entry k after k earlier assistant messages, so each script
# covers both rounds: (turn 1, turn 2, final) for round 1, then the same for round 2.
SCRIPTS = [
    _script(WRITE, PASS, RED, WRITE, PASS, RED),
    _script(PASS, PASS, RED, PASS, PASS, RED),
    _script(PASS, PASS, RED, {"action": "write_channel", "bits": "101"}, PASS, {"action": "choose", "color": "blue"}),
]


def main():
    config = GameConfig(rounds=2)  # N = 3, T = 3, B = 8
    agents = [ModelAgent(ModelConfig(name=f"scripted-agent-{i + 1}", transport="stub", model="stub",
                                     stub_texts=script)) for i, script in enumerate(SCRIPTS)]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = REPO / "reports" / "coord-game" / f"offline-demo-{stamp}"
    rollout = run_rollout(config, agents, output_dir=output_dir)
    html = save_html(rollout, output_dir / "transcript.html")
    for rnd in rollout["rounds"]:
        print(f"Round {rnd['round_index'] + 1}: choices={rnd['choices']} score={rnd['result']['score']:.2f}")
    print(f"Transcript: {html}")


if __name__ == "__main__":
    main()
