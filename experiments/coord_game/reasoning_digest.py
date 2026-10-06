"""Collect returned reasoning summaries that mention the channel into one Markdown file.

    uv run python -m experiments.coord_game.reasoning_digest reports/coord-game/*-constraints-*seed*

Reads saved rollouts only (no model calls). For each model call whose reasoning
summary matches --pattern, the digest lists the run, round, turn, agent, the
agent's private information, its action, and the round's outcome, followed by the
summary text. A table at the top counts how often each theme comes up. These are
provider summaries, not the model's full reasoning.
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .game import load_rollout
from .prompts import label

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PATTERN = r"protocol|encod|decod|mapping|convention|one-hot|index|permut|shuffl|private (list|order)|alphabet"
# Themes counted in the summary table: a name, and a pattern matched against each summary.
THEMES = {
    "private order / shuffle problem": r"permut|shuffl|private (list|order)|own (list|order)|can.?t deduce|differen\w* order",
    "position / index code": r"index|position|one-hot|slot",
    "shared reference (alphabetical, fixed global order)": r"alphabet|sorted|global (order|mapping|list)|canonical|fixed (order|mapping)",
    "copying last round's colors": r"previous round|last round|prior round|earlier round|round \d+ (results|choices)",
    "forbidden colors": r"forbid",
}


def _run_label(rollout):
    config = rollout["config"]
    effort = {m.get("effort") for m in rollout.get("models") or []}
    return (f"{config['objective']} · {config['n_agents']} agents · effort {'/'.join(str(e) for e in effort)} · "
            f"feedback {config['feedback']} · seed {config['seed']}")


def collect(paths, pattern):
    match = re.compile(pattern, re.I)
    themes = {name: re.compile(p, re.I) for name, p in THEMES.items()}
    entries, theme_counts, totals = [], Counter(), Counter()
    for path in paths:
        rollout = load_rollout(path)
        for rnd in rollout["rounds"]:
            for turn in rnd["turns"]:
                for record in turn["actions"]:
                    text = ((record.get("response") or {}).get("reasoning") or "").strip()
                    totals["calls"] += 1
                    if not text:
                        continue
                    totals["with_summary"] += 1
                    for name, theme in themes.items():
                        if theme.search(text):
                            theme_counts[name] += 1
                    if match.search(text):
                        entries.append({"run": _run_label(rollout), "folder": Path(path).name, "rnd": rnd,
                                        "turn": turn["turn_index"], "record": record, "text": text})
    return entries, theme_counts, totals


def render(entries, theme_counts, totals, pattern):
    lines = ["# Reasoning digest", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Pattern: `{pattern}`.", "",
             "These are the reasoning summaries the provider returned, not the models' full reasoning.", "",
             f"- Model calls: {totals['calls']}",
             f"- Calls with a summary: {totals['with_summary']}",
             f"- Summaries matching the pattern (listed below): {len(entries)}", "",
             "| Theme | Summaries mentioning it |", "|---|---|"]
    lines += [f"| {name} | {theme_counts[name]} of {totals['with_summary']} |" for name in THEMES]
    current = None
    for e in entries:
        if e["run"] != current:
            current = e["run"]
            lines += ["", f"## {current}", "", f"`{e['folder']}`"]
        rnd, record = e["rnd"], e["record"]
        agent = record["agent"]
        private = (rnd.get("private_info") or [None] * (agent + 1))[agent]
        result = rnd.get("result") or {}
        lines += ["", f"### Round {rnd['round_index'] + 1}, turn {e['turn'] + 1}, {label(agent)}", "",
                  f"- Private info: {private or 'none'}",
                  f"- Action: `{record.get('action') or record.get('error')}`",
                  f"- Round outcome: choices {rnd.get('choices')}, score {result.get('score', 0):.2f}", "",
                  *[f"> {line}" if line else ">" for line in e["text"].splitlines()]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", type=Path, help="rollout folders")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN, help="regex a summary must match to be listed")
    parser.add_argument("--out", type=Path, help="output file (default: reports/coord-game/analysis/...)")
    args = parser.parse_args(argv)
    entries, theme_counts, totals = collect(sorted(args.runs), args.pattern)
    out = args.out or REPO / "reports" / "coord-game" / "analysis" / \
        f"reasoning-digest-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(entries, theme_counts, totals, args.pattern), encoding="utf-8")
    print(f"{len(entries)} of {totals['with_summary']} summaries listed ({totals['calls']} calls). Digest: {out}")
    for name in THEMES:
        print(f"  {name}: {theme_counts[name]}")


if __name__ == "__main__":
    main()
