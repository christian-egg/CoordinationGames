"""Text the models see. User-owned: every string here is model input.

Step 4 adds only the tool descriptions. The system prompt, round, turn, and
report messages come in step 5. Agents are shown as 1 to N; the code uses 0 to N - 1.
"""
from __future__ import annotations

# DRAFT (step 4), for the user to review and rewrite.
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
