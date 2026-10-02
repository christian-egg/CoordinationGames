"""Text the models see. User-owned: every string here is model input.

Agents are shown as Agent 1 to Agent N; the code uses indices 0 to N - 1, and
label() is the only place that converts. Text that depends on the objective or
the channel structure is in a dict keyed by its name, so a new objective or
channel adds an entry here.

DRAFT (step 5): Claude's first version, for the user to review and rewrite.
"""
from __future__ import annotations

import json

PROMPT_VERSION = "coord-game-draft-1"


def label(agent):
    return f"Agent {agent + 1}"


# ----- Tool descriptions (step 4) -----

# write_channel's text depends on the channel structure, so it is keyed by channel name.
WRITE_DESCRIPTIONS = {
    "broadcast": ("Replace your message on your broadcast channel. Every other agent can "
                  "read it from the next turn on. This uses your action for this turn."),
}
PASS_DESCRIPTION = "Send nothing this turn. Your current message stays as it is."
CHOOSE_DESCRIPTION = ("Submit your final color for this round. This is your only choice "
                      "this round, and it is final.")
FIELD_DESCRIPTIONS = {
    "bits": "Your message: exactly {bits} characters, each 0 or 1.",
    "color": "One color from your color list for this round, spelled exactly as listed.",
}

# ----- Text keyed by objective, channel structure, and feedback level -----

OBJECTIVE_PROMPTS = {
    "matching": "All agents must try to choose the same color. Any color on the list works, "
                "as long as every agent chooses it.",
}

CHANNEL_PROMPTS = {
    "broadcast": ("Each agent has its own broadcast channel. Only you can write to yours, and "
                  "every other agent can read it. You can read every other agent's channel."),
}

# Heading for the list of messages in each turn message.
CHANNEL_VIEW_HEADINGS = {
    "broadcast": "Current messages on the other agents' channels:",
}

FEEDBACK_PROMPTS = {
    "full": "After each round, every agent is told the group's score and every agent's final color.",
    "score_only": "After each round, every agent is told the group's score, but not the other agents' colors.",
    "none": "After each round, no score or colors are reported.",
}

ACTION_FORMATS = {
    "write_channel": '{"action": "write_channel", "bits": "<exactly %d characters, each 0 or 1>"}',
    "pass": '{"action": "pass"}',
    "choose": '{"action": "choose", "color": "<one color from your list>"}',
}


# ----- Messages -----

def system_prompt(config, agent):
    """Given once, at the start of the rollout."""
    n, t = config.n_agents, config.turns
    blocks = [
        f"You are {label(agent)}, one of {n} agents (Agent 1 to Agent {n}) playing a color "
        "coordination game. The agents share one goal: in each round, the group's final colors "
        "should meet that round's objective. There is no chat. The only way to communicate is "
        "through short binary messages.",

        f"{CHANNEL_PROMPTS[config.channel]} A message is a string of exactly {config.bits} "
        "characters, each 0 or 1. The bits have no predefined meaning. A message stays on "
        "its channel until its sender replaces it. All channels are emptied at the start of each round.",
    ]
    if t == 1:
        blocks.append(f"There are {config.rounds} rounds, each with a single turn. There is no time "
                      "to send messages: on that turn, you choose your color with choose.")
    else:
        blocks.append(
            f"There are {config.rounds} rounds, each with {t} turns. All agents act at the same "
            "time on each turn, so a message sent on one turn can be read from the next turn on. "
            f"On turns 1 to {t - 1}, you take one action: write a new message with write_channel, "
            f"or send nothing with pass. On turn {t}, the final turn, you cannot send messages: "
            "you choose your color with choose.")
    blocks += [
        "Each agent chooses exactly once per round, and the choice is final. A missing or invalid "
        "choice counts as no color, which never meets the objective.",

        f"At the start of each round, you are told the objective and given a list of "
        f"{len(config.colors)} colors. Every agent gets the same colors, but each agent sees them "
        "in its own private order, which is reshuffled every round.",

        f"The group's score for a round is 1 - d/{n}, where d is the smallest number of agents "
        "who would have to change their color for the group to meet the objective. A missing "
        "choice always has to change. So the score is 1 when the objective is met. "
        f"{FEEDBACK_PROMPTS[config.feedback]} Your conversation history carries over between rounds.",
    ]
    actions = ["write_channel", "pass", "choose"] if t > 1 else ["choose"]
    formats = "\n".join(ACTION_FORMATS[a] % config.bits if a == "write_channel" else ACTION_FORMATS[a]
                        for a in actions)
    blocks.append("Return exactly one action on each turn. Action formats:\n" + formats + "\n"
                  "If action tools are supplied, call exactly one available tool with only its "
                  "declared arguments. Otherwise, return one action as a JSON object with only the "
                  "fields for that action.")
    return "\n\n".join(blocks)


def round_message(config, agent, round_index, colors, private_info=None):
    """The opening message of a round: the objective, restated every round, and this agent's colors."""
    lines = [f"Round {round_index + 1} of {config.rounds}.",
             f"Objective: {OBJECTIVE_PROMPTS[config.objective]}",
             f"Your colors this round: {json.dumps(list(colors))}"]
    if private_info is not None:  # no milestone-1 objective has private information
        raise NotImplementedError("private information text is not written yet")
    return "\n".join(lines)


def turn_message(config, agent, turn_index, view):
    """The message before each action. view comes from the channel structure."""
    t = config.turns
    final = turn_index == t - 1
    lines = [f"Turn {turn_index + 1} of {t}" + (", the final turn." if final else ".")]
    if t > 1:
        lines.append(CHANNEL_VIEW_HEADINGS[config.channel])
        lines += [f"- {label(m['sender'])}: {json.dumps(m['bits'])}" for m in view["others"]]
        lines.append(f"Your current message: {json.dumps(view['own'])}")
    if final:
        lines.append("Choose your color for this round." if t == 1 else
                     "You cannot send messages on this turn. Choose your color for this round.")
    else:
        lines.append("Take one action: write_channel or pass.")
    return "\n".join(lines)


def action_result(action, error, final_turn):
    """The reply to one action. On an error, action is None and error is its message."""
    if error is not None:
        if final_turn:
            return f"Invalid choice: {error}. You have no color this round."
        return f"Invalid action: {error}. Nothing was sent this turn."
    if action["action"] == "write_channel":
        return "Your message was sent successfully."
    if action["action"] == "pass":
        return "You sent nothing this turn."
    return f"Your choice is recorded: {action['color']}."


def round_report(config, agent, round_index, choices, result):
    """The end-of-round report for one agent, or None when feedback is "none"."""
    if config.feedback == "none":
        return None
    d, n = result["edit_distance"], config.n_agents
    lines = [f"Round {round_index + 1} results.",
             f"Group score: {result['score']:.2f} ({d} of {n} agents would have to change color)."]
    if config.feedback == "full":
        lines.append("Final colors:")
        for other, color in enumerate(choices):
            name = label(other) + (" (you)" if other == agent else "")
            lines.append(f"- {name}: {color if color is not None else 'no color'}")
    return "\n".join(lines)
