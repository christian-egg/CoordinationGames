"""Channel structures: who can write where, who reads what, and when writes land.

Agents act simultaneously within a turn. A write is staged when the agent acts and
only becomes visible when the turn is committed, after every agent has acted. So
every agent in a turn sees the same snapshot. A message stays until it is overwritten.
"""
from __future__ import annotations

import re


def valid_message(bits, n_bits):
    """True for a string of exactly n_bits characters, each 0 or 1."""
    return isinstance(bits, str) and len(bits) == n_bits and re.fullmatch(r"[01]*", bits) is not None


class Broadcast:
    """One channel per agent. Only its owner writes to it; every agent reads it."""

    name = "broadcast"

    def __init__(self, config):
        self.n_agents = config.n_agents
        self.n_bits = config.bits
        self.messages = [""] * self.n_agents  # "" means no message sent yet
        self.pending = {}
        self.sends = []  # every committed send, for bit accounting

    def reset(self):
        """Empty every channel, e.g. at the start of a round."""
        if self.pending:
            raise RuntimeError("Commit or discard staged writes before a reset")
        self.messages = [""] * self.n_agents

    def stage(self, sender, bits, recipient=None):
        """Record a write, visible only after commit. Broadcast has no recipient."""
        if type(sender) is not int or not 0 <= sender < self.n_agents:
            raise ValueError("sender must be an agent index")
        if recipient is not None:
            raise ValueError("Broadcast messages have no recipient")
        if not valid_message(bits, self.n_bits):
            raise ValueError(f"A message must be exactly {self.n_bits} characters, each 0 or 1")
        if sender in self.pending:
            raise ValueError("This agent already wrote this turn")
        self.pending[sender] = bits

    def commit(self, round_index, turn_index):
        """Make this turn's staged writes visible, and log them."""
        for sender in sorted(self.pending):
            bits = self.pending[sender]
            self.messages[sender] = bits
            self.sends.append({"round_index": round_index, "turn_index": turn_index,
                               "sender": sender, "recipient": None, "bits": bits})
        self.pending = {}

    def view(self, agent):
        """What one agent can read: its own message, and each other agent's message."""
        return {"own": self.messages[agent],
                "others": [{"sender": other, "bits": self.messages[other]}
                           for other in range(self.n_agents) if other != agent]}

    def bits_sent(self, round_index, agent):
        """Bits this agent sent in one round: B per committed send."""
        return sum(len(s["bits"]) for s in self.sends
                   if s["round_index"] == round_index and s["sender"] == agent)


# None marks a planned channel structure that is not built yet.
REGISTRY = {"broadcast": Broadcast, "peer_to_peer": None}


def get_channel(name, config):
    if name not in REGISTRY:
        raise ValueError(f"Unknown channel structure {name!r}")
    if REGISTRY[name] is None:
        raise NotImplementedError(f"channel {name!r} is not implemented yet")
    return REGISTRY[name](config)
