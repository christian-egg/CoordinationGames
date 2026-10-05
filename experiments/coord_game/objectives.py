"""Group objectives and their edit-distance scoring.

A final assignment is one entry per agent: a color, or None for an empty choice
(no valid choice was made). The edit distance d is the minimum number of agents
whose color must change for the assignment to meet the objective. An empty choice
always needs a change. The round score is 1 - d / N.

The objective's text for the models lives in prompts.py, with the other model-visible text.
"""
from __future__ import annotations

from collections import Counter


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

    def edit_distance(self, choices, config, private_info):
        raise NotImplementedError

    def result(self, choices, config, private_info, colors=None):
        """Validate a final assignment against this round's colors and score it."""
        colors = config.colors if colors is None else colors
        choices = list(choices)
        if len(choices) != config.n_agents:
            raise ValueError("choices must have one entry per agent")
        if any(c is not None and c not in colors for c in choices):
            raise ValueError("Each choice must be a listed color or None")
        distance = self.edit_distance(choices, config, private_info)
        if type(distance) is not int or not 0 <= distance <= config.n_agents:
            raise ValueError("edit distance must be an integer in [0, N]")
        return {"edit_distance": distance, "score": score(distance, config.n_agents)}


class Matching(Objective):
    """All agents must choose the same color."""

    name = "matching"

    def edit_distance(self, choices, config, private_info):
        # Keep the largest group of one color; every other agent, including
        # every empty choice, must change.
        counts = Counter(c for c in choices if c is not None)
        largest = max(counts.values(), default=0)
        return len(choices) - largest


def score(edit_distance, n_agents):
    """1 for a passing assignment, 0 when every agent must change."""
    return 1 - edit_distance / n_agents


# None marks a planned objective that is not built yet.
REGISTRY = {"matching": Matching, "unique": None, "dichotomy": None,
            "majority": None, "constraints": None}


def get_objective(name):
    if name not in REGISTRY:
        raise ValueError(f"Unknown objective {name!r}")
    if REGISTRY[name] is None:
        raise NotImplementedError(f"objective {name!r} is not implemented yet")
    return REGISTRY[name]()
