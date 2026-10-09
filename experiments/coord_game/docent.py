"""Convert a saved coordination-game rollout into a Docent AgentRun. No I/O.

One transcript per agent: its system prompt and its exact private history, in
order. The reasoning a model returned is attached to its response for analysis,
marked as not replayed: the model never saw its own past reasoning. Scores and
other agents' colors are run metadata; they reach an agent only through the
report messages already in its history. Adapted from
experiments/color_game/docent.py in ethanelasky/collusion-on-the-open-web.
"""
from __future__ import annotations

import json
from copy import deepcopy

from .prompts import label

EXPORT_SCHEMA = "coord-game-docent/v1"
TERMINAL_STATUSES = {"complete", "complete_with_errors", "failed", "interrupted"}


def export_key(rollout_id):
    """A stable identity for a rollout's export. Docent assigns its own IDs."""
    return f"{EXPORT_SCHEMA}:{rollout_id}"


def condition_tags(rollout):
    """Tags naming the experimental condition, e.g. ["feedback:full", "effort:medium"].
    Each tag is also a top-level metadata field, for filtering in Docent."""
    config = rollout["config"]
    tags = [f"objective:{config['objective']}", f"feedback:{config['feedback']}", f"agents:{config['n_agents']}",
            # Rollouts saved before carry_reasoning existed did not carry reasoning.
            f"reasoning:{'carried' if config.get('carry_reasoning', False) else 'not_carried'}"]
    efforts = {m.get("effort") for m in rollout.get("models") or []} - {None}
    if efforts:  # omitted when unknown (e.g. scripted agents)
        tags.append(f"effort:{efforts.pop() if len(efforts) == 1 else 'mixed'}")
    return tags


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _response_text(response):
    text = response.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(response["action"]) if isinstance(response.get("action"), dict) else ""


def rollout_to_agent_run(rollout):
    """Build an AgentRun. Raises ValueError if the saved histories and records disagree."""
    from docent.data_models import AgentRun, Transcript
    from docent.data_models.chat import parse_chat_message
    from docent.data_models.chat.content import ContentReasoning, ContentText

    _require(rollout.get("schema") == "coord-game/v1", "Not a coord-game/v1 rollout")
    status = rollout.get("status")
    _require(status in TERMINAL_STATUSES, "Only a finished rollout can be exported")
    rollout_id = rollout["rollout_id"]
    config, summary = rollout["config"], rollout.get("summary") or {}
    n = config["n_agents"]
    systems, histories = rollout["system_prompts"], rollout["agents"]
    _require(len(systems) == n and len(histories) == n, "Need a system prompt and history for every agent")
    models = rollout.get("models") or [{}] * n
    rounds = rollout.get("rounds") or []

    transcripts = []
    for agent in range(n):
        history = histories[agent]["messages"]
        model = models[agent] if agent < len(models) else {}
        # Records of this agent's saved responses, in the order they entered its history.
        answered = [(rnd["round_index"], turn["turn_index"], record)
                    for rnd in rounds for turn in rnd["turns"] for record in turn["actions"]
                    if record["agent"] == agent and record.get("response") is not None]
        answers = iter(answered)

        def chat(role, text, metadata, reasoning=None):
            content = [ContentText(text=text)]
            if reasoning:
                content.insert(0, ContentReasoning(reasoning=reasoning))
            fields = {"role": role, "content": content, "metadata": deepcopy(metadata)}
            if role == "assistant" and model.get("model"):
                fields["model"] = model["model"]
            return parse_chat_message(fields)

        messages = [chat("system", systems[agent], {"provenance": "system", "observed_by_agent": True})]
        for index, message in enumerate(history):
            meta = {"history_message_index": index, "observed_by_agent": True}
            if message["role"] == "user":
                messages.append(chat("user", message["content"], {**meta, "provenance": "game_message"}))
                continue
            round_index, turn_index, record = next(answers, (None, None, None))
            _require(record is not None and _response_text(record["response"]) == message["content"],
                     f"{label(agent)}'s history does not match its saved responses")
            response = record["response"]
            messages.append(chat("assistant", message["content"], {
                **meta, "provenance": "model_response", "round_index": round_index, "turn_index": turn_index,
                "action": record.get("action"), "error": record.get("error"),
                "reasoning_replayed_to_model": False,
                "usage": response.get("usage"), "finish_reason": response.get("finish_reason"),
            }, response.get("reasoning")))
        _require(next(answers, None) is None, f"{label(agent)} has saved responses missing from its history")
        transcripts.append(Transcript(
            name=label(agent), messages=messages,
            description=f"{label(agent)}'s exact private history. Reasoning is shown for analysis only.",
            metadata={"agent_index": agent, "agent_label": label(agent), "model": deepcopy(model)}))

    model_names = list(dict.fromkeys(m.get("name") or m.get("model") or "unknown model" for m in models))
    met, mean = summary.get("objective_met"), summary.get("mean_score")
    metadata = {
        "export_schema": EXPORT_SCHEMA, "export_key": export_key(rollout_id),
        "rollout_id": rollout_id, "status": status,
        "prompt_version": rollout.get("prompt_version"), "config": config, "summary": summary,
        "model_alias": " / ".join(model_names), "source": rollout.get("source"),
        **dict(tag.split(":", 1) for tag in condition_tags(rollout)), "tags": condition_tags(rollout),
        "rounds": [{key: rnd.get(key) for key in ("round_index", "choices", "result", "bits_sent", "sends",
                                                   "colors", "color_orders", "private_info",
                                                   "valid_for_analysis", "errors")}
                   for rnd in rounds],
        "reasoning_note": "Returned reasoning is attached for analysis. It was never replayed to the model.",
    }
    partial = "" if status.startswith("complete") else "[PARTIAL] "
    score = "—" if mean is None else f"{mean:.2f}"
    return AgentRun(
        name=(f"{partial}{' / '.join(model_names)} | {n} agents | {config['channel']} | {config['objective']} | "
              f"feedback {config['feedback']} | seed {config['seed']} | score {score} | met {met}/{config['rounds']}"),
        description="One transcript per agent. Scores and other agents' choices are research metadata.",
        transcripts=transcripts, metadata=json.loads(json.dumps(metadata, default=str)))
