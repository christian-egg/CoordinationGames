# Diplomacy cost baseline

This folder compares the cost of LLM Diplomacy games with coordination-game rollouts. The
games run in our fork of [GoodStartLabs/AI_Diplomacy](https://github.com/GoodStartLabs/AI_Diplomacy):
[christian-egg/AI_Diplomacy](https://github.com/christian-egg/AI_Diplomacy), branch `collusion`.
Everything about Diplomacy itself lives there, in
[`COLLUSION.md`](https://github.com/christian-egg/AI_Diplomacy/blob/collusion/COLLUSION.md):
setup, running games, the changes from upstream (numbered 1–5 below), the transcript viewer
(`ai_diplomacy/dashboard.py`) and the collusion metrics (`ai_diplomacy/collusion_metrics.py`).

This folder holds only `cost_summary.py`, which reads both kinds of runs.

We picked AI_Diplomacy because it already supports OpenRouter and per-power models.
[joehahn/diplomacy-A2A](https://github.com/joehahn/diplomacy-A2A) has a nicer transcript
viewer, whose layout the fork's dashboard adapts, but only talks to Anthropic models.

## Measured costs

All games use 7 powers, 3 negotiation rounds, and `max_tokens` 16000. Costs are billed
amounts from `openrouter_usage.jsonl`. For the 10-09 runs, they match the change in the
key's spend counter.

| Run | Date | Model, effort | Years | Changes used | Calls | Input cached | Cost | Time |
|---|---|---|---|---|---|---|---|---|
| `luna_medium_1902` | 10-09 | Luna 5.6, medium | 1901–02 | items 1–3, 5 | 192 | 0% | $0.30 | 4 min |
| `luna_medium_1910` | 10-09 | Luna 5.6, medium | 1901–10 | items 1–3, 5 | 953 | 0% | $1.75 | 28 min |
| `luna_medium_1910_seedlast` | 10-10 | Luna 5.6, medium | stopped early | seed moved only | 119 | 0% | $0.17 | 3 min |
| `luna_medium_1910_cached` | 10-10 | Luna 5.6, medium | 1901–10 | items 1–5 | 954 | 26% | $1.57 | 29 min |
| `luna_high_1910_cached` | 10-10 | Luna 5.6, high | 1901–10 | items 1–5 | 908 | 27% | $2.55 | 77 min |
| `sol_high_1902_cached` | 10-10 | Sol 5.6, high | 1901–02 | items 1–5 | 191 | 23% | $3.86 | 13 min |
| `luna_high_2y_ops4` | 10-13 | Luna 5.6, high | 1901–02 | items 1–5 + collusion game, 4 operatives | 206 | 22% | $0.49 | 15 min |

For comparison, coordination-game rollouts (5 rounds × 3 turns, Luna 5.6). These costs are
estimated by pricing logged token counts at list prices; summed over all rollouts, the
estimate came within 2% of the key's lifetime spend.

| Rollouts | Effort | Count | Mean cost |
|---|---|---|---|
| 3 agents | medium | 40 | $0.037 |
| 3 agents | high | 32 | $0.079 |
| 5 agents | medium | 8 | $0.054 |
| 5 agents | high | 8 | $0.128 |

A full medium-effort Diplomacy game with caching ($1.57) costs about as much as 42
three-agent or 29 five-agent medium-effort rollouts.

To regenerate both tables:

```bash
uv run python -m experiments.diplomacy.cost_summary ~/AI_Diplomacy/results/*/ reports/coord-game/*/
```
