"""Extract structured actions from Claude's response."""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger("arlo.assistant.extractors")


def extract_actions(response_text: str) -> tuple[str, list[dict]]:
    """Extract actions from Claude's response.

    Returns (clean_text, actions_list).
    clean_text has the <actions> block removed.
    actions_list is a list of action dicts.
    """
    # Find <actions>...</actions> block
    pattern = r"<actions>\s*(.*?)\s*</actions>"
    match = re.search(pattern, response_text, re.DOTALL)

    if not match:
        return response_text.strip(), []

    actions_json = match.group(1).strip()
    clean_text = re.sub(pattern, "", response_text, flags=re.DOTALL).strip()

    try:
        actions = json.loads(actions_json)
        if not isinstance(actions, list):
            actions = [actions]
        logger.info("Extracted %d actions from response", len(actions))
        return clean_text, actions
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse actions JSON: %s", e)
        return clean_text, []
