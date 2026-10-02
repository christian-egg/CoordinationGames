"""Offline checks for channel structures."""
import pytest

from experiments.coord_game import GameConfig
from experiments.coord_game.channels import REGISTRY, get_channel, valid_message
from experiments.coord_game.config import CHANNELS, IMPLEMENTED_CHANNELS


CONFIG = GameConfig(bits=4)  # N = 3


def broadcast():
    return get_channel("broadcast", CONFIG)


def test_channels_start_empty():
    channel = broadcast()
    assert channel.view(0) == {"own": "", "others": [{"sender": 1, "bits": ""}, {"sender": 2, "bits": ""}]}


def test_writes_are_hidden_until_commit():
    channel = broadcast()
    channel.stage(0, "1010")
    assert channel.view(1)["others"][0]["bits"] == ""  # same turn: not visible yet
    assert channel.view(0)["own"] == ""
    channel.commit(0, 0)
    assert channel.view(1)["others"] == [{"sender": 0, "bits": "1010"}, {"sender": 2, "bits": ""}]
    assert channel.view(0)["own"] == "1010"


def test_messages_persist_until_overwritten_and_reset():
    channel = broadcast()
    channel.stage(2, "0001")
    channel.commit(0, 0)
    channel.commit(0, 1)  # nobody wrote: the message stays
    assert channel.view(0)["others"][1]["bits"] == "0001"
    channel.stage(2, "1111")
    channel.commit(0, 2)
    assert channel.view(0)["others"][1]["bits"] == "1111"
    channel.reset()
    assert channel.view(0)["others"][1]["bits"] == ""


@pytest.mark.parametrize("bits", ["101", "10101", "10a1", "", 1010, None])
def test_messages_must_be_exactly_b_bits(bits):
    with pytest.raises(ValueError):
        broadcast().stage(0, bits)


def test_stage_rejects_bad_writes():
    channel = broadcast()
    with pytest.raises(ValueError):
        channel.stage(3, "0000")  # no such agent
    with pytest.raises(ValueError):
        channel.stage(0, "0000", recipient=1)  # broadcast has no recipient
    channel.stage(0, "0000")
    with pytest.raises(ValueError):
        channel.stage(0, "1111")  # one write per turn
    with pytest.raises(RuntimeError):
        channel.reset()  # staged write not yet committed


def test_bit_accounting():
    channel = broadcast()
    channel.stage(0, "0000")
    channel.stage(1, "1111")
    channel.commit(0, 0)
    channel.stage(0, "0000")  # resending the same message still costs B bits
    channel.commit(0, 1)
    channel.stage(0, "1000")
    channel.commit(1, 0)
    assert [channel.bits_sent(0, a) for a in range(3)] == [8, 4, 0]
    assert channel.bits_sent(1, 0) == 4
    assert [(s["round_index"], s["turn_index"], s["sender"]) for s in channel.sends] == [
        (0, 0, 0), (0, 0, 1), (0, 1, 0), (1, 0, 0)]


def test_valid_message():
    assert valid_message("0110", 4) and not valid_message("0110", 3) and not valid_message("0120", 4)


def test_registry_agrees_with_config():
    assert set(REGISTRY) == set(CHANNELS)
    assert {name for name, cls in REGISTRY.items() if cls is not None} == set(IMPLEMENTED_CHANNELS)
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        get_channel("peer_to_peer", CONFIG)
    with pytest.raises(ValueError):
        get_channel("telepathy", CONFIG)
