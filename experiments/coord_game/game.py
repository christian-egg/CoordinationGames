"""The rollout loop for the N-agent coordination game.

One rollout is R rounds of T turns. Each agent keeps its own conversation history
for the whole rollout: nothing is summarized, truncated, or reset between rounds.

Outputs, in output_dir:
- events.jsonl: the journal, one line per event, flushed as it happens. It keeps
  every request and response even if the run dies mid-round.
- rollout.json: the full record, checkpointed after every round.
- source/: a copy of the game code that produced the run.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ai_collusion.client import model_error_details
from ai_collusion.run_storage import write_json

from .actions import available_actions, check_rules, normalise_response, parse_action, tool_definitions
from .channels import get_channel
from .config import GameConfig, color_orders
from .objectives import get_objective
from .prompts import (PROMPT_VERSION, action_result, round_message, round_report, system_prompt,
                      turn_message)

SCHEMA = "coord-game/v1"


class Journal:
    """Append-only event log. Copied from the color game's _Journal."""

    def __init__(self, path, on_event=None):
        self.file = Path(path).open("x", encoding="utf-8")  # never overwrite a journal
        self.lock = threading.Lock()
        self.on_event = on_event
        self.index = 0

    def write(self, kind, **data):
        with self.lock:
            event = {"event_index": self.index, "kind": kind, "time_unix_s": time.time(), **data}
            self.file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.file.flush()
            os.fsync(self.file.fileno())
            self.index += 1
            if self.on_event is not None:
                self.on_event(copy.deepcopy(event))

    def close(self):
        self.file.close()


def _source_info(output_dir):
    """Hash and copy the code that produced this run."""
    directory = Path(__file__).parent
    root = directory.parents[1]
    hashes = {}
    for path in [*sorted(directory.glob("*.py")), root / "ai_collusion/client.py"]:
        relative = path.relative_to(root)
        contents = path.read_bytes()
        hashes[str(relative)] = hashlib.sha256(contents).hexdigest()
        saved = Path(output_dir) / "source" / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(contents)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=directory,
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"git_commit": commit, "module_sha256": hashes}


def _metadata(agent):
    if hasattr(agent, "metadata"):
        return agent.metadata()
    return {"callable": getattr(agent, "__name__", type(agent).__name__)}


def run_rollout(config: GameConfig, agents, *, output_dir, on_event=None) -> dict:
    """Run one rollout. agents[i] is a callable that receives agent i's private request.

    Calls within a turn are made one after another, but every agent sees the
    same snapshot: writes are staged and only committed after the whole turn.
    Raw responses are journaled before parsing. Model API errors are saved and
    mark the round invalid for analysis; nothing is retried or replaced.
    """
    if not isinstance(config, GameConfig):
        raise TypeError("config must be a GameConfig")
    config.require_implemented()  # before any model call or file
    agents = list(agents)
    if len(agents) != config.n_agents or not all(callable(a) for a in agents):
        raise ValueError("agents must be a list of n_agents callables")
    directory = Path(output_dir).expanduser().resolve()
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)

    n = config.n_agents
    objective = get_objective(config.objective)
    channel = get_channel(config.channel, config)
    systems = [system_prompt(config, i) for i in range(n)]
    histories = [[] for _ in range(n)]
    journal = Journal(directory / "events.jsonl", on_event)
    rollout = {
        "schema": SCHEMA, "rollout_id": str(uuid.uuid4()), "status": "running",
        "created_utc": datetime.now(timezone.utc).isoformat(), "prompt_version": PROMPT_VERSION,
        "config": config.to_dict(), "system_prompts": systems,
        "source": _source_info(directory), "models": [_metadata(a) for a in agents],
        "rounds": [], "agents": [], "summary": {},
        "artifact_paths": {"json": str(directory / "rollout.json"), "jsonl": str(directory / "events.jsonl")},
    }
    infrastructure_errors = []

    def call(agent, request, record):
        """Call one agent. Return its normalized response, or None after an API error."""
        started = time.monotonic()
        try:
            response = normalise_response(agents[agent](copy.deepcopy(request)))
            json.dumps(response)  # must be serializable before it reaches state
        except Exception as exc:
            # Do not save arbitrary exception text; an SDK error may contain credentials.
            error = {"type": type(exc).__name__, "category": "model_api", **model_error_details(exc)}
            record.update(error=error, elapsed_s=time.monotonic() - started)
            journal.write("model_error", agent=agent, round_index=request["round_index"],
                          turn_index=request["turn_index"], error=error)
            return None
        # Journal before parsing, so a malformed response is never lost.
        record.update(response=response, elapsed_s=time.monotonic() - started)
        journal.write("response", agent=agent, round_index=request["round_index"],
                      turn_index=request["turn_index"], response=response)
        return response

    def play_turn(rnd, round_index, turn_index):
        actions = available_actions(config, turn_index)
        tools = tool_definitions(actions, config, channel)
        final = turn_index == config.turns - 1
        views = [channel.view(i) for i in range(n)]  # one snapshot for the whole turn
        turn = {"turn_index": turn_index, "views": views, "actions": []}
        rnd["turns"].append(turn)
        for agent in range(n):
            histories[agent].append({"role": "user", "content": turn_message(config, agent, turn_index, views[agent])})
            request = {"agent": agent, "system": systems[agent], "messages": copy.deepcopy(histories[agent]),
                       "round_index": round_index, "turn_index": turn_index,
                       "available_actions": actions, "tools": tools}
            record = {"agent": agent, "request_messages": request["messages"], "response": None,
                      "action": None, "error": None, "result_message": None}
            turn["actions"].append(record)
            journal.write("request", **copy.deepcopy(request))
            response = call(agent, request, record)
            if response is None:  # API error: not the model's doing, so it sees no reply
                rnd["valid_for_analysis"] = False
                rnd["errors"].append({"agent": agent, "turn_index": turn_index, **record["error"]})
                infrastructure_errors.append(record["error"])
                continue
            text = response.get("text")
            if not isinstance(text, str):
                text = json.dumps(response["action"]) if isinstance(response.get("action"), dict) else ""
            histories[agent].append({"role": "assistant", "content": text})
            try:
                action = check_rules(parse_action(response, actions, channel), config, rnd["colors"])
            except ValueError as exc:
                # An invalid write counts as a pass; an invalid choice leaves no color.
                record["error"] = {"type": "InvalidAction", "category": "action", "message": str(exc)}
                rnd["errors"].append({"agent": agent, "turn_index": turn_index, **record["error"]})
                message = action_result(None, str(exc), final)
            else:
                record["action"] = action
                if action["action"] == "write_channel":
                    channel.stage(agent, action["bits"])
                elif action["action"] == "choose":
                    rnd["choices"][agent] = action["color"]
                message = action_result(action, None, final)
            record["result_message"] = message
            histories[agent].append({"role": "user", "content": message})
            journal.write("action_result", agent=agent, round_index=round_index, turn_index=turn_index,
                          action=record["action"], error=record["error"], message=message)
        channel.commit(round_index, turn_index)  # this turn's writes become visible together

    def finish():
        rollout["agents"] = [{"messages": copy.deepcopy(h)} for h in histories]
        scored = [r for r in rollout["rounds"] if "result" in r]
        valid = [r for r in scored if r["valid_for_analysis"]]
        mean = lambda rounds: sum(r["result"]["score"] for r in rounds) / len(rounds) if rounds else None
        rollout["summary"] = {
            "rounds": config.rounds, "scored_rounds": len(scored), "valid_rounds": len(valid),
            "mean_score": mean(scored), "valid_mean_score": mean(valid),
            "objective_met": sum(r["result"]["edit_distance"] == 0 for r in scored),
            "invalid_actions": sum(e["category"] == "action" for r in rollout["rounds"] for e in r["errors"]),
            "empty_choices": sum(c is None for r in scored for c in r["choices"]),
            "infrastructure_errors": len(infrastructure_errors),
            "bits_sent": [sum(r["bits_sent"][i] for r in scored) for i in range(n)],
        }
        rollout["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(directory / "rollout.json", rollout)

    try:
        journal.write("rollout_start", metadata=copy.deepcopy(rollout))
        for round_index in range(config.rounds):
            channel.reset()  # channels are emptied every round
            colors = objective.round_colors(config, round_index)
            orders = color_orders(config, round_index, colors)
            private = objective.private_info(config, round_index)
            rnd = {"round_index": round_index, "colors": list(colors), "color_orders": [list(o) for o in orders],
                   "private_info": private, "turns": [], "choices": [None] * n,
                   "errors": [], "valid_for_analysis": True}
            rollout["rounds"].append(rnd)
            for agent in range(n):
                histories[agent].append({"role": "user", "content": round_message(
                    config, agent, round_index, orders[agent], private[agent])})
            journal.write("round_start", round_index=round_index, colors=rnd["colors"],
                          color_orders=rnd["color_orders"], private_info=private)
            for turn_index in range(config.turns):
                play_turn(rnd, round_index, turn_index)
            rnd["result"] = objective.result(rnd["choices"], config, private, colors)
            rnd["bits_sent"] = [channel.bits_sent(round_index, i) for i in range(n)]
            rnd["sends"] = [s for s in channel.sends if s["round_index"] == round_index]
            for agent in range(n):
                report = round_report(config, agent, round_index, rnd["choices"], rnd["result"])
                if report is not None:
                    histories[agent].append({"role": "user", "content": report})
            journal.write("round_end", round_index=round_index, choices=rnd["choices"],
                          result=rnd["result"], valid_for_analysis=rnd["valid_for_analysis"])
            finish()  # checkpoint after every round
        rollout["status"] = "complete_with_errors" if infrastructure_errors else "complete"
        journal.write("rollout_end", status=rollout["status"])
    except BaseException as exc:
        rollout["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        rollout["fatal_error"] = {"type": type(exc).__name__}
        journal.write("rollout_error", status=rollout["status"], error=rollout["fatal_error"])
        raise
    finally:
        finish()
        journal.close()
    return rollout


def load_rollout(path) -> dict:
    path = Path(path).expanduser()
    if path.is_dir():
        path = path / "rollout.json"
    rollout = json.loads(path.read_text(encoding="utf-8"))
    if rollout.get("schema") != SCHEMA:
        raise ValueError(f"Not a {SCHEMA} rollout: {path}")
    return rollout
