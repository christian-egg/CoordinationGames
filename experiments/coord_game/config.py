"""Settings for the N-agent coordination game, and its seeded color shuffles."""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, fields

COLORS = ("red", "green", "blue", "yellow", "orange", "purple", "pink", "brown")

# Every planned option is accepted here; IMPLEMENTED_* lists the ones the game can run.
CHANNELS = ("broadcast", "peer_to_peer")
OBJECTIVES = ("matching", "unique", "dichotomy", "majority", "constraints")
FEEDBACK = ("full", "score_only", "none")
IMPLEMENTED_CHANNELS = ("broadcast",)
IMPLEMENTED_OBJECTIVES = OBJECTIVES


@dataclass(frozen=True)
class GameConfig:
    n_agents: int = 3
    colors: tuple[str, ...] = COLORS
    rounds: int = 5  # R
    turns: int = 3  # T; the final turn is for choosing only
    bits: int = 8  # B, the length of one message
    actions_per_turn: int = 1  # A
    channel: str = "broadcast"
    objective: str = "matching"
    feedback: str = "full"
    seed: int = 0

    def __post_init__(self):
        object.__setattr__(self, "colors", tuple(self.colors))
        for name in ("n_agents", "rounds", "turns", "bits", "actions_per_turn"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.n_agents < 2:
            raise ValueError("n_agents must be at least 2")
        if len(self.colors) < 2 or len(set(self.colors)) != len(self.colors):
            raise ValueError("Use at least two distinct colors")
        if any(not isinstance(c, str) or not c.strip() or c != c.strip() for c in self.colors):
            raise ValueError("Each color must be a nonempty string without outer spaces")
        if len({c.casefold() for c in self.colors}) != len(self.colors):
            raise ValueError("Colors must differ by more than capitalization")
        for name, options in (("channel", CHANNELS), ("objective", OBJECTIVES), ("feedback", FEEDBACK)):
            if getattr(self, name) not in options:
                raise ValueError(f"{name} must be one of {options}")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        # Unique needs N + 1 colors; Constraints forbids a different color per agent.
        if self.objective in ("unique", "constraints") and self.n_agents >= len(self.colors):
            raise ValueError(f"{self.objective} needs fewer agents than colors "
                             f"({self.n_agents} agents, {len(self.colors)} colors)")

    def require_implemented(self):
        """Raise before any model call if this config uses a planned but unbuilt option."""
        if self.channel not in IMPLEMENTED_CHANNELS:
            raise NotImplementedError(f"channel {self.channel!r} is not implemented yet")
        if self.objective not in IMPLEMENTED_OBJECTIVES:
            raise NotImplementedError(f"objective {self.objective!r} is not implemented yet")
        if self.actions_per_turn != 1:
            raise NotImplementedError("actions_per_turn other than 1 is not implemented yet")

    def to_dict(self):
        return {**asdict(self), "colors": list(self.colors)}

    @classmethod
    def from_dict(cls, data):
        """Rebuild a saved config. Missing or unknown fields are errors, not defaults."""
        names = {f.name for f in fields(cls)}
        if set(data) != names:
            missing, unknown = sorted(names - set(data)), sorted(set(data) - names)
            raise ValueError(f"Config fields do not match: missing {missing}, unknown {unknown}")
        return cls(**data)


def color_orders(config: GameConfig, round_index: int, colors=None) -> list[tuple[str, ...]]:
    """Each agent's private, shuffled order of this round's colors (default: all colors).

    A fresh shuffle every round, reproducible from the seed. String seeds are
    hashed deterministically, so the order doesn't depend on PYTHONHASHSEED.
    """
    if type(round_index) is not int or not 0 <= round_index < config.rounds:
        raise ValueError("round_index must be an integer in [0, rounds)")
    orders = []
    for agent in range(config.n_agents):
        order = list(config.colors if colors is None else colors)
        random.Random(f"coord-game-v1:{config.seed}:round-{round_index}:agent-{agent}").shuffle(order)
        orders.append(tuple(order))
    return orders
