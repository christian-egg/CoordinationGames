"""Summarize model-call cost for AI_Diplomacy games and coordination-game rollouts.

    uv run python -m experiments.diplomacy.cost_summary ~/AI_Diplomacy/results/*/
    uv run python -m experiments.diplomacy.cost_summary reports/coord-game/*/

Reads saved runs only (no model calls).

- AI_Diplomacy runs: reads `openrouter_usage.jsonl`, written by ai_diplomacy.patch.
  Each line holds the cost OpenRouter billed for that call, so these totals are exact.
- Coordination-game rollouts: reads `events.jsonl` and prices the token counts at the
  list prices below, since the rollouts don't record billed cost. Rollouts are grouped
  by agent count and effort. Only complete rollouts on a priced model are counted.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

# OpenRouter list prices in USD per token (checked 2026-10-09).
PRICES = {
    "openai/gpt-5.6-luna": {"input": 0.20e-6, "cached": 0.02e-6, "output": 1.20e-6},
}


def _cached(usage: dict) -> int:
    return (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0


def _reasoning(usage: dict) -> int:
    return (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0


def diplomacy_run(run_dir: Path) -> dict:
    """Totals for one AI_Diplomacy run, from its openrouter_usage.jsonl."""
    rows = [json.loads(line) for line in (run_dir / "openrouter_usage.jsonl").read_text().splitlines() if line]
    usages = [r["usage"] for r in rows]
    return {
        "calls": len(usages),
        "prompt": sum(u["prompt_tokens"] for u in usages),
        "cached": sum(_cached(u) for u in usages),
        "completion": sum(u["completion_tokens"] for u in usages),
        "reasoning": sum(_reasoning(u) for u in usages),
        "cost": sum(u.get("cost") or 0 for u in usages),
        "minutes": (rows[-1]["t"] - rows[0]["t"]) / 60 if rows else 0,
    }


def coord_rollout(run_dir: Path) -> tuple[tuple[int, str], float] | None:
    """(n_agents, effort) and estimated cost for one complete rollout, or None to skip it."""
    rollout = json.loads((run_dir / "rollout.json").read_text())
    models = {m["model"] for m in rollout.get("models") or []}
    if rollout.get("status") != "complete" or len(models) != 1 or next(iter(models)) not in PRICES:
        return None
    price = PRICES[next(iter(models))]
    effort = "/".join(sorted({str(m.get("effort")) for m in rollout["models"]}))
    cost = 0.0
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        usage = (event.get("response") or {}).get("usage") if event["kind"] == "response" else None
        if usage:
            cached = _cached(usage)
            cost += ((usage["prompt_tokens"] - cached) * price["input"] + cached * price["cached"]
                     + usage["completion_tokens"] * price["output"])
    return (rollout["config"]["n_agents"], effort), cost


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", type=Path, help="AI_Diplomacy run dirs and/or coord-game rollout dirs")
    args = parser.parse_args()

    groups: dict[tuple[int, str], list[float]] = defaultdict(list)
    for run_dir in args.runs:
        if (run_dir / "openrouter_usage.jsonl").exists():
            t = diplomacy_run(run_dir)
            print(f"{run_dir.name}: {t['calls']} calls, {t['prompt']:,} input tokens "
                  f"({100 * t['cached'] / max(t['prompt'], 1):.0f}% cached), {t['completion']:,} output "
                  f"({t['reasoning']:,} reasoning), ${t['cost']:.3f}, {t['minutes']:.0f} min")
        elif (run_dir / "events.jsonl").exists() and (run_dir / "rollout.json").exists():
            result = coord_rollout(run_dir)
            if result:
                groups[result[0]].append(result[1])
    for (n_agents, effort), costs in sorted(groups.items()):
        print(f"coord game, {n_agents} agents, effort {effort}: {len(costs)} rollouts, "
              f"mean ${statistics.mean(costs):.4f} (min ${min(costs):.4f}, max ${max(costs):.4f}), estimated")


if __name__ == "__main__":
    main()
