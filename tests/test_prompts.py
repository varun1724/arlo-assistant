"""Test system prompt building."""

import pytest
from app.llm.prompts import build_system_prompt


def test_builds_prompt_with_all_context():
    prompt = build_system_prompt(
        profile_summary="- health/protein_goal: 180g\n- fitness/gym_schedule: daily",
        health_today="Steps: 5000, Protein: 85g",
        pending_tasks="- [high] Buy groceries (due 2026-04-01)",
        recent_messages="user: How much protein have I had?\nassistant: You've had 85g so far.",
    )
    assert "Arlo" in prompt
    assert "180g" in prompt
    assert "Steps: 5000" in prompt
    assert "Buy groceries" in prompt
    assert "85g so far" in prompt
    assert "<actions>" in prompt  # instruction for action format


def test_builds_prompt_with_empty_context():
    prompt = build_system_prompt(
        profile_summary="",
        health_today="",
        pending_tasks="",
        recent_messages="",
    )
    assert "Arlo" in prompt
    assert "No profile data" in prompt
    assert "No health data" in prompt
    assert "No pending tasks" in prompt
    assert "start of a new conversation" in prompt


def test_includes_time_of_day():
    prompt = build_system_prompt("", "", "", "")
    # Should include current time and day
    assert "CURRENT TIME" in prompt


def test_includes_action_format_instructions():
    prompt = build_system_prompt("", "", "", "")
    assert "profile_update" in prompt
    assert "log_meal" in prompt
    assert "create_task" in prompt
    assert "save_knowledge" in prompt
    assert "create_reminder" in prompt
