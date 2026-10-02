"""Offline checks for objective scoring."""
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
