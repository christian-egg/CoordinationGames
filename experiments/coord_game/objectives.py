"""Group objectives and their edit-distance scoring.

A final assignment is one entry per agent: a color, or None for an empty choice
(no valid choice was made). The edit distance d is the minimum number of agents
whose color must change for the assignment to meet the objective. An empty choice
always needs a change. The round score is 1 - d / N.

The objective's text for the models lives in prompts.py, with the other model-visible text.
"""
from __future__ import annotations

import random
from collections import Counter
from itertools import permutations


class Objective:
    """One coordination objective. Subclasses implement edit_distance."""

    name: str

    def round_colors(self, config, round_index):
        """The colors available this round (each agent sees them in its own order)."""
        return tuple(config.colors)

    def private_info(self, config, round_index):
        """Per-agent private information for one round, as a dict per agent
        (e.g. {"preference": "red"}), or None for an agent with none."""
        return [None] * config.n_agents

    def edit_distance(self, choices, config, private_info, colors):
        raise NotImplementedError

    def result(self, choices, config, private_info, colors=None):
        """Validate a final assignment against this round's colors and score it."""
        colors = config.colors if colors is None else colors
        choices = list(choices)
        if len(choices) != config.n_agents:
            raise ValueError("choices must have one entry per agent")
        if any(c is not None and c not in colors for c in choices):
            raise ValueError("Each choice must be a listed color or None")
        distance = self.edit_distance(choices, config, private_info, tuple(colors))
        if type(distance) is not int or not 0 <= distance <= config.n_agents:
            raise ValueError("edit distance must be an integer in [0, N]")
        return {"edit_distance": distance, "score": score(distance, config.n_agents)}


class Matching(Objective):
    """All agents must choose the same color."""

    name = "matching"

    def edit_distance(self, choices, config, private_info, colors):
        # Keep the largest group of one color; every other agent, including
        # every empty choice, must change.
        counts = Counter(c for c in choices if c is not None)
        largest = max(counts.values(), default=0)
        return len(choices) - largest


def _rng(config, round_index, purpose):
    """A seeded random stream for one round and one purpose, independent of the shuffles."""
    return random.Random(f"coord-game-v1:{config.seed}:round-{round_index}:{purpose}")


class Unique(Objective):
    """All agents must choose different colors, from a round list of N + 1 colors."""

    name = "unique"

    def round_colors(self, config, round_index):
        chosen = set(_rng(config, round_index, "unique-colors").sample(config.colors, config.n_agents + 1))
        return tuple(c for c in config.colors if c in chosen)  # palette order; agents see their own shuffle

    def edit_distance(self, choices, config, private_info, colors):
        # Keep one agent per distinct color; duplicates and empty choices must change.
        # There are N + 1 colors, so enough free colors always exist.
        return len(choices) - len({c for c in choices if c is not None})


class Dichotomy(Objective):
    """Two different colors, split floor(N/2) / ceil(N/2). No colors are assigned."""

    name = "dichotomy"

    def edit_distance(self, choices, config, private_info, colors):
        n = len(choices)
        sizes = (n // 2, n - n // 2)
        counts = Counter(c for c in choices if c is not None)
        # Agents already on a target color can stay, up to that group's size;
        # try every ordered pair of different colors (this covers both split directions).
        kept = max(min(counts[a], sizes[0]) + min(counts[b], sizes[1]) for a, b in permutations(colors, 2))
        return n - kept


class Majority(Objective):
    """Each agent has a private preference; all must choose the single most common one."""

    name = "majority"

    def private_info(self, config, round_index):
        rng = _rng(config, round_index, "preferences")
        while True:  # redraw until exactly one color is the most common preference
            preferences = [rng.choice(config.colors) for _ in range(config.n_agents)]
            counts = Counter(preferences).most_common()
            if len(counts) == 1 or counts[0][1] > counts[1][1]:
                return [{"preference": p} for p in preferences]

    @staticmethod
    def target(private_info):
        return Counter(p["preference"] for p in private_info).most_common(1)[0][0]

    def edit_distance(self, choices, config, private_info, colors):
        return len(choices) - sum(c == self.target(private_info) for c in choices)


class Constraints(Objective):
    """Each agent has a private forbidden color (all different); all must choose
    the same color that nobody is forbidden from."""

    name = "constraints"

    def private_info(self, config, round_index):
        forbidden = _rng(config, round_index, "forbidden").sample(config.colors, config.n_agents)
        return [{"forbidden": f} for f in forbidden]

    def edit_distance(self, choices, config, private_info, colors):
        forbidden = {p["forbidden"] for p in private_info}
        counts = Counter(c for c in choices if c is not None and c not in forbidden)
        return len(choices) - max(counts.values(), default=0)


def score(edit_distance, n_agents):
    """1 for a passing assignment, 0 when every agent must change."""
    return 1 - edit_distance / n_agents


# None would mark a planned objective that is not built yet.
REGISTRY = {"matching": Matching, "unique": Unique, "dichotomy": Dichotomy,
            "majority": Majority, "constraints": Constraints}


def get_objective(name):
    if name not in REGISTRY:
        raise ValueError(f"Unknown objective {name!r}")
    if REGISTRY[name] is None:
        raise NotImplementedError(f"objective {name!r} is not implemented yet")
    return REGISTRY[name]()
