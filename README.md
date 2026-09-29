# Color guessing game

This repository contains only the color guessing game from
[*Encoded Coordination on the Open Web*](https://www.lesswrong.com/posts/SCdR7W6L5GvKaEzaZ/encoded-coordination-on-the-open-web)
(Ethan Elasky, Can Küçükkurt, Frank Nakasako, David Africa). The original
repository, [ethanelasky/collusion-on-the-open-web](https://github.com/ethanelasky/collusion-on-the-open-web),
also has the wiki incident replay, the covert-channel sender/receiver
experiment, the stress suite, and the classifiers. Those were removed here. The
`main` branch keeps the full original release.

In the game, Alice and Bob see the same ordered list of eight colors. Each round,
Alice is privately assigned a color and must submit it. Bob does not see the
assignment and scores a match if he submits the same color. There are three
settings. In `guessing_only`, the players cannot communicate. In
`async_counter` (Alice acts first, then Bob) and `sync_counter` (both act
under a shared 180-second deadline), both players can read a shared CounterAPI
counter, and only Alice can increment it. The default is five rounds with
eight actions per player each round.

## Quick start

```bash
uv sync                       # Python 3.11+
uv run pytest                 # offline; makes no model API calls
```

Set `OPENAI_API_KEY` (and any other keys that
[experiments/color_game/models.yaml](experiments/color_game/models.yaml) names)
in the shell or in a `.env` at the repository root.

**Platform:** The campaign runner and request pool use `fcntl`, which only works
on Linux and macOS. On Windows, run the code in WSL.

## Layout

| Path | Contents |
|---|---|
| [experiments/color_game/](experiments/color_game) | Game engine, prompts, model adapter, counter environment, campaign CLI, reports, and Docent export ([README](experiments/color_game/README.md)) |
| [ai_collusion/](ai_collusion) | Shared support code: model client and retries (`client`), CounterAPI mock (`counter`), request pacing and pooling, 401 stop, atomic JSON storage, and model/.env loading |
| [notebooks/](notebooks) | Single-rollout notebooks for changing prompts and reading transcripts |
| [scripts/](scripts) | Offline analysis and plotting for saved campaigns (these need `scipy`/`matplotlib`) |
| [docs/color-game.md](docs/color-game.md), [docs/color-game/](docs/color-game) | Game design and the September 2026 result reports |
| [tests/](tests) | Offline tests for all of the above |

Start with [the game design](docs/color-game.md) and
[the single-rollout notebook](notebooks/color_game.ipynb). For repeated runs, use
the [campaign CLI](experiments/color_game/README.md):

```bash
uv run python -m experiments.color_game.cli launch --out reports/color-game/example \
  --rollouts 50 --workers 50 --rounds 5 --actions-per-agent 8
```

### Authentication failures stop the experiment

A model API **401 Unauthorized** prints a fatal error, and the experiment exits
with a nonzero code. The request is not retried, and the stop applies to every
model worker in the process. See `ai_collusion/auth_stop.py`.
