"""Test the action extractor that parses Claude's responses."""

import pytest
from app.llm.extractors import extract_actions


def test_no_actions():
    text = "Here's your answer. No actions needed."
    clean, actions = extract_actions(text)
    assert clean == text
    assert actions == []


def test_single_action():
    text = '''Here's your plan.

<actions>
[{"type": "create_task", "title": "Buy groceries", "priority": "high"}]
</actions>'''
    clean, actions = extract_actions(text)
    assert "Buy groceries" not in clean
    assert "<actions>" not in clean
    assert len(actions) == 1
    assert actions[0]["type"] == "create_task"
    assert actions[0]["title"] == "Buy groceries"


def test_multiple_actions():
    text = '''Got it, I'll track that.

<actions>
[
  {"type": "profile_update", "category": "nutrition", "key": "protein_goal", "value": "180g"},
  {"type": "log_meal", "description": "3 eggs", "protein_g": 18, "calories": 210}
]
</actions>'''
    clean, actions = extract_actions(text)
    assert len(actions) == 2
    assert actions[0]["type"] == "profile_update"
    assert actions[1]["type"] == "log_meal"
    assert "Got it" in clean


def test_malformed_json_returns_empty():
    text = '''Response here.

<actions>
not valid json
</actions>'''
    clean, actions = extract_actions(text)
    assert actions == []
    assert "Response here" in clean


def test_clean_text_preserves_content():
    text = '''I logged your meal. You've had 85g of protein today, which is 47% of your 180g goal. Keep it up!

<actions>
[{"type": "log_meal", "description": "chicken breast", "protein_g": 45, "calories": 280}]
</actions>'''
    clean, actions = extract_actions(text)
    assert "85g of protein" in clean
    assert "47%" in clean
    assert "<actions>" not in clean
    assert len(actions) == 1


def test_reminder_action():
    text = '''I'll remind you.

<actions>
[{"type": "create_reminder", "message": "Go for a walk", "smart_condition": {"type": "steps_below", "threshold": 8000, "after_hour": 16}}]
</actions>'''
    clean, actions = extract_actions(text)
    assert len(actions) == 1
    assert actions[0]["smart_condition"]["threshold"] == 8000


def test_knowledge_action():
    text = '''I'll remember that!

<actions>
[{"type": "save_knowledge", "category": "preference", "content": "User's favorite restaurant is Olive Garden"}]
</actions>'''
    clean, actions = extract_actions(text)
    assert actions[0]["content"] == "User's favorite restaurant is Olive Garden"
