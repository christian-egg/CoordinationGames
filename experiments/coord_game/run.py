"""Run rollouts with a real model. Each rollout makes paid API calls.

    uv run python -m experiments.coord_game.run --model luna-openrouter
    uv run python -m experiments.coord_game.run --model luna-openrouter --effort high --rollouts 3

--model names an entry in the models file (default: experiments/coord_game/models.yaml).
Every agent uses its own ModelAgent with the same model config. The API key is
read from .env or the shell, by the variable name in the models file.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from ai_collusion.runner import load_models

from .config import GameConfig
from .game import run_rollout
from .model import ModelAgent
from .prompts import label
from .view import save_html

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MODELS = REPO / "experiments" / "coord_game" / "models.yaml"
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")


def progress(event):
    """Researcher-side progress lines. This never changes what agents see."""
    kind = event["kind"]
    if kind == "round_start":
        print(f"  Round {event['round_index'] + 1} started", flush=True)
    elif kind == "action_result":
        action = event["action"] or {"action": "invalid"}
        detail = action.get("bits") or action.get("color") or ""
        print(f"    turn {event['turn_index'] + 1} {label(event['agent'])}: {action['action']} {detail}".rstrip(),
              flush=True)
    elif kind == "model_error":
        print(f"    turn {event['turn_index'] + 1} {label(event['agent'])}: API error "
              f"{event['error'].get('type')}", flush=True)
    elif kind == "round_end":
        print(f"  Round {event['round_index'] + 1}: choices={event['choices']} "
              f"score={event['result']['score']:.2f}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="model name from the models file")
    parser.add_argument("--models-file", type=Path, default=DEFAULT_MODELS)
    parser.add_argument("--effort", choices=EFFORTS, default="medium",
                        help="reasoning effort, overriding the models file (default: medium)")
    parser.add_argument("--rollouts", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0, help="seed of the first rollout; later ones add 1 each")
    args = parser.parse_args(argv)

    model = load_models(args.models_file, only=[args.model])[0]  # also loads .env
    model = replace(model, effort=args.effort, name=f"{args.model}@{args.effort}")
    if model.api_key_env and not os.environ.get(model.api_key_env):
        raise SystemExit(f"{model.api_key_env} is not set. Add it to {REPO / '.env'} or your shell.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for index in range(args.rollouts):
        config = GameConfig(seed=args.seed + index)
        calls = config.n_agents * config.rounds * config.turns
        output_dir = REPO / "reports" / "coord-game" / f"{stamp}-{args.model}-{args.effort}-seed{config.seed}"
        print(f"Rollout {index + 1}/{args.rollouts}: {model.model}, effort {args.effort}, "
              f"seed {config.seed}, {calls} calls -> {output_dir}", flush=True)
        agents = [ModelAgent(model) for _ in range(config.n_agents)]
        rollout = None
        try:
            rollout = run_rollout(config, agents, output_dir=output_dir, on_event=progress)
        finally:
            # Save a transcript even after a failure or Ctrl-C; rollout.json is checkpointed per round.
            if rollout is None and (output_dir / "rollout.json").exists():
                from .game import load_rollout
                rollout = load_rollout(output_dir)
            if rollout is not None:
                print(f"Status: {rollout['status']} · mean score: {rollout['summary'].get('mean_score')}")
                print(f"Transcript: {save_html(rollout, output_dir / 'transcript.html')}", flush=True)


if __name__ == "__main__":
    main()
