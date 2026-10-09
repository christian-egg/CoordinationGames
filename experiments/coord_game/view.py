"""Standalone HTML and notebook views of one coordination-game rollout.

The view is for the researcher: it shows every agent's private history side by
side. The game never shows this combined view to any agent. All model text is
escaped, so a response cannot inject HTML or scripts. No network is needed.
Escaping helpers, styles, and layout are adapted from the color game's
experiments/color_game/view.py in ethanelasky/collusion-on-the-open-web.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from .prompts import label


def _escape(value):
    return html.escape(str(value))


def _pre(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return f"<pre>{_escape(text)}</pre>"


def _details(summary, value, *, opened=False):
    if value is None:
        return ""
    return f"<details{' open' if opened else ''}><summary>{_escape(summary)}</summary>{_pre(value)}</details>"


def _messages(messages):
    return "".join(f"<div class='message'><strong>{_escape(m.get('role'))}</strong>{_pre(m.get('content'))}</div>"
                   for m in messages or [])


def _usage(rollout):
    responses = [a.get("response") or {} for r in rollout.get("rounds") or []
                 for t in r.get("turns") or [] for a in t.get("actions") or []]
    usages = [r.get("usage") or {} for r in responses]
    costs = [u["cost"] for u in usages if isinstance(u.get("cost"), (int, float)) and not isinstance(u["cost"], bool)]
    return {"saved_responses": sum(bool(r) for r in responses),
            "prompt_tokens": sum(u.get("prompt_tokens", u.get("input_tokens", 0)) or 0 for u in usages),
            "completion_tokens": sum(u.get("completion_tokens", u.get("output_tokens", 0)) or 0 for u in usages),
            "reported_cost_usd": sum(costs) if costs else None}


def _color(choice):
    return _escape(choice) if choice is not None else "<span class='error'>no color</span>"


def _messages_sent(rnd, n):
    """Each agent's messages sent this round, in order, with the bits they used."""
    lines = []
    for agent in range(n):
        sent = [s["bits"] for s in rnd.get("sends") or [] if s["sender"] == agent]
        text = ", ".join(f"<code>{_escape(json.dumps(b))}</code>" for b in sent) or "none"
        lines.append(f"{label(agent)}: {text} ({sum(map(len, sent))} bits)")
    return "<br>".join(lines)


def _action_summary(record):
    """One line per agent per turn: what it did, or why it failed."""
    action, error = record.get("action"), record.get("error")
    if error:
        return f"<span class='error'>{_escape(error.get('category'))} error: {_escape(error.get('message', error.get('type')))}</span>"
    if action is None:
        return "—"
    if action["action"] == "write_channel":
        return f"write <code>{_escape(action['bits'])}</code>"
    if action["action"] == "choose":
        return f"choose <strong>{_escape(action['color'])}</strong>"
    return "pass"


def _turn_panel(turn, n_turns):
    t = turn["turn_index"]
    parts = [f"<h4>Turn {t + 1} of {n_turns}{' (final)' if t == n_turns - 1 else ''}</h4>",
             "<table><thead><tr><th>Agent</th><th>Own message at start</th><th>Action</th>"
             "<th>Reply shown</th></tr></thead><tbody>"]
    for record, view in zip(turn["actions"], turn["views"]):
        parts.append(f"<tr><td>{label(record['agent'])}</td><td><code>{_escape(json.dumps(view['own']))}</code></td>"
                     f"<td>{_action_summary(record)}</td><td>{_escape(record.get('result_message') or '—')}</td></tr>")
    parts.append("</tbody></table>")
    for record in turn["actions"]:
        response = record.get("response") or {}
        parts.append(f"<details><summary>{label(record['agent'])}: input, response, and reasoning</summary>"
                     "<div class='inner'><strong>Exact input for this call</strong>"
                     f"{_messages(record.get('request_messages'))}"
                     f"{_details('Returned reasoning', response.get('reasoning'), opened=True)}"
                     f"{_details('Full saved response', response)}</div></details>")
    return "".join(parts)


def _round_panel(rnd, config):
    i, result = rnd["round_index"], rnd.get("result") or {}
    validity = "" if rnd.get("valid_for_analysis", True) else " · <span class='error'>invalid for analysis</span>"
    parts = [f"<section id='round-{i + 1}' class='round'><h3>Round {i + 1} · score "
             f"{result.get('score', 0):.2f}{validity}</h3>",
             "<p>" + " · ".join(f"{label(a)}: <strong>{_color(c)}</strong>"
                                for a, c in enumerate(rnd.get("choices") or [])) + "</p>",
             _details("Each agent's private color order", {label(a): o for a, o in enumerate(rnd.get("color_orders") or [])}),
             _details("Each agent's private information",
                      {label(a): p for a, p in enumerate(rnd.get("private_info") or []) if p is not None} or None)]
    for turn in rnd.get("turns") or []:
        parts.append(_turn_panel(turn, config.get("turns", len(rnd["turns"]))))
    parts += [_details("Round errors", rnd.get("errors") or None, opened=True),
              _details("Full round record", {k: v for k, v in rnd.items() if k != "turns"}), "</section>"]
    return "".join(parts)


_STYLE = """
.coord-game { color: #17263c; font: 15px/1.5 system-ui, sans-serif; max-width: 1180px;
  margin: 0 auto; padding: 20px; background: #fff; }
.coord-game h1 { font-size: 27px; margin-bottom: 8px; }
.coord-game h2 { font-size: 21px; margin-top: 28px; }
.coord-game h3 { font-size: 19px; }
.coord-game h4 { font-size: 16px; margin: 20px 0 8px; }
.coord-game .muted { color: #526174; }
.coord-game table { border-collapse: collapse; width: 100%; margin: 10px 0; }
.coord-game th, .coord-game td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #dce3eb; }
.coord-game th { background: #eef3f8; }
.coord-game pre { white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.5 ui-monospace,
  SFMono-Regular, Menlo, monospace; background: #f5f7fa; border-radius: 6px;
  padding: 10px; max-height: 550px; overflow: auto; }
.coord-game code { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
.coord-game details { margin: 8px 0; }
.coord-game summary { cursor: pointer; color: #1b5692; font-weight: 600; }
.coord-game .inner { border-left: 3px solid #4d729b; padding-left: 12px; }
.coord-game .round { border-top: 2px solid #dce3eb; margin-top: 28px; }
.coord-game .error { color: #a83232; }
.coord-game .message { border-left: 2px solid #dce3eb; padding-left: 10px; margin: 10px 0; }
.coord-game a { color: #1b5692; }
@media (max-width: 700px) { .coord-game { padding: 10px; } }
"""


def render_rollout(rollout, *, full_document=True):
    """Render a saved rollout. full_document=False returns a fragment for a notebook cell."""
    config, summary = rollout.get("config") or {}, rollout.get("summary") or {}
    rounds = rollout.get("rounds") or []
    n = config.get("n_agents", 0)
    usage = _usage(rollout)
    cost = usage["reported_cost_usd"]
    mean = summary.get("mean_score")
    title = f"Coordination game · {rollout.get('rollout_id', 'one rollout')}"
    parts = [f"<style>{_STYLE}</style><main class='coord-game'><h1>{_escape(title)}</h1>",
             f"<p>{n} agents · {_escape(config.get('channel'))} · {_escape(config.get('objective'))} · "
             f"R={_escape(config.get('rounds'))}, T={_escape(config.get('turns'))}, B={_escape(config.get('bits'))}, "
             f"A={_escape(config.get('actions_per_turn'))} · feedback: {_escape(config.get('feedback'))} · "
             f"prompts: {_escape(rollout.get('prompt_version'))} · status: {_escape(rollout.get('status'))}</p>",
             f"<p><strong>Mean score: {'—' if mean is None else f'{mean:.2f}'}</strong> · objective met in "
             f"{_escape(summary.get('objective_met', 0))}/{len(rounds)} rounds · invalid actions: "
             f"{_escape(summary.get('invalid_actions', 0))} · API errors: {_escape(summary.get('infrastructure_errors', 0))} · "
             f"provider-reported cost: {'not reported' if cost is None else f'${cost:.6f}'}</p>",
             "<p class='muted'>Researcher view: it shows every agent's private history. "
             "No agent sees this combined view. A missing cost field is not zero cost.</p>",
             _details("Configuration and metadata", {k: v for k, v in rollout.items() if k not in ("rounds", "agents")}),
             _details("Saved-response usage", usage),
             "<table><thead><tr><th>Round</th>" + "".join(f"<th>{label(a)}</th>" for a in range(n)) +
             "<th>Edit distance</th><th>Score</th><th>Messages sent</th><th>Errors</th></tr></thead><tbody>"]
    for rnd in rounds:
        result = rnd.get("result") or {}
        i = rnd["round_index"]
        score = f"{result['score']:.2f}" if "score" in result else "—"
        parts.append(f"<tr><td><a href='#round-{i + 1}'>{i + 1}</a></td>"
                     + "".join(f"<td>{_color(c)}</td>" for c in rnd.get("choices") or [])
                     + f"<td>{_escape(result.get('edit_distance', '—'))}</td>"
                     f"<td>{score}</td>"
                     f"<td>{_messages_sent(rnd, n)}</td><td>{len(rnd.get('errors') or [])}</td></tr>")
    parts.append("</tbody></table>")
    parts += [_round_panel(rnd, config) for rnd in rounds]
    systems = rollout.get("system_prompts") or []
    histories = rollout.get("agents") or []
    if histories:
        parts.append("<h2>Final private histories</h2>")
        for a, history in enumerate(histories):
            parts.append(f"<details><summary>{label(a)}</summary><div class='inner'>"
                         f"{_details('System prompt', systems[a] if a < len(systems) else None)}"
                         f"{_messages(history.get('messages'))}</div></details>")
    parts.append("</main>")
    body = "".join(parts)
    if not full_document:
        return body
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_escape(title)}</title></head><body>{body}</body></html>")


def save_html(rollout, path):
    """Save a self-contained researcher view."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_rollout(rollout), encoding="utf-8")
    return path


def show_rollout(rollout):
    """Display one rollout in Jupyter."""
    from IPython.display import HTML, display

    display(HTML(render_rollout(rollout, full_document=False)))
