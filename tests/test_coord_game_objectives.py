"""Offline checks for objective scoring."""
from collections import Counter

import pytest

from experiments.coord_game import GameConfig
from experiments.coord_game.config import IMPLEMENTED_OBJECTIVES, OBJECTIVES
from experiments.coord_game.objectives import REGISTRY, get_objective, score


CONFIG = GameConfig()  # N = 3


@pytest.mark.parametrize("choices, distance", [
    (["red", "red", "red"], 0),        # all match
    (["red", "red", "blue"], 1),
    (["red", "blue", "green"], 2),     # all different: one agent already "matches"
    (["red", "red", None], 1),         # an empty choice must always change
    (["red", None, None], 2),
    ([None, None, None], 3),           # all empty
])
def test_matching_edit_distance_and_score(choices, distance):
    result = get_objective("matching").result(choices, CONFIG, [None] * 3)
    assert result == {"edit_distance": distance, "score": 1 - distance / 3}


def test_score_bounds():
    assert score(0, 4) == 1 and score(4, 4) == 0 and score(1, 4) == 0.75


@pytest.mark.parametrize("choices", [["red", "red"], ["red", "red", "teal"], ["red", "red", ""]])
def test_invalid_assignments_are_rejected(choices):
    with pytest.raises(ValueError):
        get_objective("matching").result(choices, CONFIG, [None] * 3)


def test_matching_has_no_private_info():
    assert get_objective("matching").private_info(CONFIG, 0) == [None, None, None]


def test_registry_agrees_with_config():
    assert set(REGISTRY) == set(OBJECTIVES)
    assert {name for name, cls in REGISTRY.items() if cls is not None} == set(IMPLEMENTED_OBJECTIVES)
    for name in set(OBJECTIVES) - set(IMPLEMENTED_OBJECTIVES):
        with pytest.raises(NotImplementedError, match="not implemented yet"):
            get_objective(name)
    with pytest.raises(ValueError):
        get_objective("anything")


# ----- Milestone 2 objectives (N = 3 unless noted) -----

def score_of(name, choices, config=CONFIG, private=None, round_index=0):
    objective = get_objective(name)
    private = objective.private_info(config, round_index) if private is None else private
    colors = objective.round_colors(config, round_index)
    return objective.result(choices, config, private, colors)["edit_distance"]


def test_unique_colors_and_distance():
    config = GameConfig(objective="unique")
    unique = get_objective("unique")
    colors = unique.round_colors(config, 0)
    assert len(colors) == 4 and set(colors) <= set(config.colors)
    assert unique.round_colors(config, 0) == colors != unique.round_colors(config, 1)  # seeded, fresh per round
    a, b, c, _ = colors
    assert score_of("unique", [a, b, c], config) == 0
    assert score_of("unique", [a, a, b], config) == 1
    assert score_of("unique", [a, a, a], config) == 2
    assert score_of("unique", [a, None, None], config) == 2
    with pytest.raises(ValueError):  # a color outside this round's 4
        score_of("unique", [next(x for x in config.colors if x not in colors), a, b], config)


@pytest.mark.parametrize("n, choices, distance", [
    (3, ["red", "red", "blue"], 0),             # 2 / 1 split
    (3, ["red", "blue", "blue"], 0),            # either color can be bigger
    (3, ["red", "red", "red"], 1),
    (3, ["red", "blue", "green"], 1),
    (3, [None, None, None], 3),
    (4, ["red", "red", "blue", "blue"], 0),
    (4, ["red", "red", "red", "blue"], 1),
    (4, ["red", "red", "red", "red"], 2),
    (4, ["red", "blue", "green", None], 2),
    (2, ["red", "blue"], 0),
    (2, ["red", "red"], 1),
])
def test_dichotomy_distance(n, choices, distance):
    assert score_of("dichotomy", choices, GameConfig(n_agents=n)) == distance


def test_majority_preferences_have_one_most_common_color():
    majority = get_objective("majority")
    for seed in range(30):
        for n in (2, 3, 4, 5):
            config = GameConfig(n_agents=n, seed=seed)
            counts = Counter(p["preference"] for p in majority.private_info(config, 0)).most_common()
            assert len(counts) == 1 or counts[0][1] > counts[1][1]
    config = GameConfig(seed=1)
    assert majority.private_info(config, 0) == majority.private_info(config, 0)  # seeded


def test_majority_distance():
    private = [{"preference": "red"}, {"preference": "red"}, {"preference": "blue"}]
    assert score_of("majority", ["red", "red", "red"], private=private) == 0
    assert score_of("majority", ["blue", "blue", "blue"], private=private) == 3  # matching, but not the majority
    assert score_of("majority", ["red", "blue", None], private=private) == 2


def test_constraints_forbidden_colors_and_distance():
    constraints = get_objective("constraints")
    config = GameConfig(objective="constraints", n_agents=7)
    forbidden = [p["forbidden"] for p in constraints.private_info(config, 0)]
    assert len(set(forbidden)) == 7  # all different
    private = [{"forbidden": "red"}, {"forbidden": "blue"}, {"forbidden": "green"}]
    assert score_of("constraints", ["pink", "pink", "pink"], private=private) == 0
    assert score_of("constraints", ["red", "red", "red"], private=private) == 3  # all on a forbidden color
    assert score_of("constraints", ["pink", "pink", "red"], private=private) == 1
    assert score_of("constraints", ["pink", "brown", None], private=private) == 2
