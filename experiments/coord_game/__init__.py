"""N-agent coordination game over bit-limited channels."""
from .config import COLORS, GameConfig, color_orders
from .game import load_rollout, run_rollout

__all__ = ["COLORS", "GameConfig", "color_orders", "load_rollout", "run_rollout"]
