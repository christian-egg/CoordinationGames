"""Offline checks for the coordination-game config and color shuffles."""
import json
from dataclasses import replace

import pytest

from experiments.coord_game import COLORS, GameConfig, color_orders


def test_defaults_are_milestone_one():
    config = GameConfig()
    assert (config.n_agents, config.rounds, config.turns, config.bits, config.actions_per_turn) == (3, 5, 3, 8, 1)
    assert (config.channel, config.objective, config.feedback) == ("broadcast", "matching", "full")
    assert config.colors == COLORS and len(COLORS) == 8
    config.require_implemented()


@pytest.mark.parametrize("field, value", [
    ("n_agents", 1), ("n_agents", 2.0), ("rounds", 0), ("turns", 0), ("bits", 0),
    ("bits", True), ("actions_per_turn", 0), ("channel", "telepathy"),
    ("objective", "anything"), ("feedback", "partial"), ("seed", "1"),
    ("colors", ("red",)), ("colors", ("red", "red")), ("colors", ("red", " blue")),
    ("colors", ("red", "Red")),
])
def test_invalid_values_are_rejected(field, value):
    with pytest.raises(ValueError):
        GameConfig(**{field: value})


@pytest.mark.parametrize("change", [
    {"channel": "peer_to_peer"}, {"objective": "unique"}, {"objective": "dichotomy"},
    {"objective": "majority"}, {"objective": "constraints"}, {"actions_per_turn": 2},
])
def test_planned_options_build_but_cannot_run(change):
    config = GameConfig(**change)  # a valid config that can be saved and inspected
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        config.require_implemented()


def test_dict_round_trip_is_strict():
    config = GameConfig(n_agents=4, colors=("a", "b", "c"), seed=9)
    saved = json.loads(json.dumps(config.to_dict()))
    assert GameConfig.from_dict(saved) == config
    with pytest.raises(ValueError, match="missing"):
        GameConfig.from_dict({k: v for k, v in saved.items() if k != "bits"})
    with pytest.raises(ValueError, match="unknown"):
        GameConfig.from_dict({**saved, "old_field": 1})


def test_color_orders_are_private_fresh_and_reproducible():
    config = GameConfig(seed=3)
    round0, round1 = color_orders(config, 0), color_orders(config, 1)
    assert len(round0) == config.n_agents
    assert all(sorted(order) == sorted(COLORS) for order in round0 + round1)
    assert len(set(round0)) == config.n_agents  # each agent has its own order
    assert round0 != round1  # reshuffled every round
    assert color_orders(config, 0) == round0  # same seed, same orders
    assert color_orders(replace(config, seed=4), 0) != round0
    for bad in (-1, config.rounds, 1.0):
        with pytest.raises(ValueError):
            color_orders(config, bad)


@pytest.mark.parametrize("objective", ["unique", "constraints"])
def test_unique_and_constraints_need_fewer_agents_than_colors(objective):
    GameConfig(objective=objective, n_agents=7)  # 7 agents, 8 colors: allowed
    with pytest.raises(ValueError, match="fewer agents than colors"):
        GameConfig(objective=objective, n_agents=8)
    GameConfig(objective=objective, n_agents=8, colors=tuple("abcdefghi"))  # 9 colors: allowed
    GameConfig(objective="matching", n_agents=8)  # other objectives have no limit
