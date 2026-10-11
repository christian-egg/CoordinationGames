# Diplomacy cost baseline

This folder checks how much a full LLM game of Diplomacy costs, as a reference point for
coordination-game rollouts. The game itself is
[GoodStartLabs/AI_Diplomacy](https://github.com/GoodStartLabs/AI_Diplomacy). Its code is
not copied here; this folder holds only what's needed to rebuild our setup:

- `ai_diplomacy.patch`: our changes to upstream commit `736a0a9` (2026-06-01).
- `cost_summary.py`: totals the cost of Diplomacy runs and coordination-game rollouts.
- `dashboard.py`: turns a game into static HTML pages for reading the trajectory.

We picked AI_Diplomacy because it already supports OpenRouter and per-power models.
[joehahn/diplomacy-A2A](https://github.com/joehahn/diplomacy-A2A) has a nicer transcript
viewer, but only talks to Anthropic models.

## Setup

AI_Diplomacy lives outside this repo (we use `~/AI_Diplomacy`). It needs Python 3.13; with
uv's default 3.14, the pinned pillow has no wheel and the build fails.

```bash
git clone https://github.com/GoodStartLabs/AI_Diplomacy.git ~/AI_Diplomacy
cd ~/AI_Diplomacy
git checkout 736a0a9
git apply ~/CoordinationGames/experiments/diplomacy/ai_diplomacy.patch
uv sync --python 3.13
```

## Running a game

The OpenRouter key comes from this repo's `.env`. Effort and the usage log are read from
environment variables added by the patch. Effort is not written to the run's own files, so
name the run folder after it.

```bash
cd ~/AI_Diplomacy
set -a && . ~/CoordinationGames/.env && set +a
RUN=results/luna_medium_1910
mkdir -p $RUN
export OPENROUTER_REASONING_EFFORT=medium OPENROUTER_USAGE_LOG=$PWD/$RUN/openrouter_usage.jsonl
M=openrouter:openai/gpt-5.6-luna
uv run python lm_game.py --max_year 1910 --num_negotiation_rounds 3 \
  --models "$M,$M,$M,$M,$M,$M,$M" --run_dir $RUN
```

`--max_year` is inclusive, so 1910 plays ten years. `--num_negotiation_rounds` defaults to
0 (no talking); 3 matches the upstream README examples.

## What the patch changes

All changes are in `OpenRouterClient` (`ai_diplomacy/clients.py`), apart from the prompt fix.

1. **Reasoning effort.** Upstream sends no effort setting to OpenRouter. The patch sends
   `reasoning_effort` from `OPENROUTER_REASONING_EFFORT`, the same field
   `experiments/coord_game/model.py` sends.
2. **Temperature.** Upstream hard-codes `temperature=0`. The patch leaves it at the provider
   default, matching our `temperature: null`.
3. **Cost logging.** Each call's usage, including the cost OpenRouter billed, is appended
   to `OPENROUTER_USAGE_LOG`.
4. **Prompt caching.** Upstream puts a random seed at the very top of every system prompt,
   so no two prompts share a beginning and nothing can be cached. The patch moves the seed
   to the end of the user message. It also splits each negotiation prompt at
   `Messages This Round` and marks the first part as a cache breakpoint. The text the model
   sees is the same, just sent as two parts. Moving the seed alone gave 0% cache hits
   (`luna_medium_1910_seedlast`); the breakpoint is what makes caching work.
5. **Empty prompt fix.** Upstream's `prompts_simple/initial_state_prompt.txt` is an empty
   file, so at the start of the game every power was asked for goals and relationships with
   no instructions, and answered with move orders instead. The patch fills it with upstream's
   own JSON version from `prompts/prompts_hold_reduction_v3/`.

## Measured costs

All games use 7 powers, 3 negotiation rounds, and `max_tokens` 16000. Costs are billed
amounts from `openrouter_usage.jsonl`. For the 10-09 runs, they match the change in the
key's spend counter.

| Run | Date | Model, effort | Years | Patch version | Calls | Input cached | Cost | Time |
|---|---|---|---|---|---|---|---|---|
| `luna_medium_1902` | 10-09 | Luna 5.6, medium | 1901–02 | items 1–3, 5 | 192 | 0% | $0.30 | 4 min |
| `luna_medium_1910` | 10-09 | Luna 5.6, medium | 1901–10 | items 1–3, 5 | 953 | 0% | $1.75 | 28 min |
| `luna_medium_1910_seedlast` | 10-10 | Luna 5.6, medium | stopped early | seed moved only | 119 | 0% | $0.17 | 3 min |
| `luna_medium_1910_cached` | 10-10 | Luna 5.6, medium | 1901–10 | full patch | 954 | 26% | $1.57 | 29 min |
| `luna_high_1910_cached` | 10-10 | Luna 5.6, high | 1901–10 | full patch | 908 | 27% | $2.55 | 77 min |
| `sol_high_1902_cached` | 10-10 | Sol 5.6, high | 1901–02 | full patch | 191 | 23% | $3.86 | 13 min |

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

## Reading a game

`dashboard.py` writes a static site into `<run>/dashboard/`, using a layout adapted from
diplomacy-A2A's transcript viewer (MIT license). Open `index.html` in a browser; no server
is needed.

```bash
uv run --project ~/AI_Diplomacy python -m experiments.diplomacy.dashboard ~/AI_Diplomacy/results/luna_medium_1910
```

`--project ~/AI_Diplomacy` runs the script in AI_Diplomacy's environment, because the maps
are drawn with the `diplomacy` engine bundled there. `--no-maps` skips the maps.

- **Index:** settings and cost, final standings, supply centers by year, and a list of
  turns showing message and invalid-order counts.
- **Turn pages:** one per movement phase, also covering the retreats and builds that
  follow it. Each has:
  - an orders map (arrows show moves) and a result map;
  - every order with its result, including invalid orders that were dropped;
  - supply centers gained and lost;
  - each power's two diary entries (written after the talks and after the results);
  - a matrix of how each power rates the others, and each power's goals.
- **Negotiation pages:** a 7×7 table of how many messages each pair exchanged. Clicking a
  cell shows only that pair's conversation, laid out in two columns with one row per round
  (R1–R3). Public messages get their own section.

The maps come from replaying the recorded orders through the engine. The script checks the
replayed board against the recorded one in every phase, and stops drawing maps if they
ever differ.

## Things to know about the outputs

- **Files.** Each run folder has:
  - `lmvsgame.json`: the trajectory (board state, orders, results, messages, and each
    power's goals, relationships and diary, per phase).
  - `llm_responses.csv`: every prompt and raw response.
  - `general_game.log` and `overview.jsonl` (settings and model assignment).
- **No reasoning text.** The client keeps only the final answer, so reasoning is billed but
  not saved.
- **No round numbers.** Messages record only a timestamp. Rounds can be recovered because
  each round's messages are added together after all powers reply: within a phase, a gap of
  more than a second marks a new round.
- **Invalid orders.** In `luna_medium_1910`, 63 of 183 order submissions had at least one
  invalid order, usually one. The engine drops just those orders. `lmvsgame.json` keeps only
  the valid ones; the invalid ones are in the `success` column of `llm_responses.csv`.
- **3D replay.** Upstream's viewer is in `ai_animation/`. To open a game automatically,
  copy its `lmvsgame.json` to `ai_animation/public/games/0/game.json`, then run
  `npm install && npm run dev` in that folder.
