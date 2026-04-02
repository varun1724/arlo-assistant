"""Full API test suite — hits the live running service at localhost:8002.

Run with: python3 tests/test_full_api.py
Requires: docker compose up -d (arlo-assistant running on port 8002)
"""

import json
import sys
import time
import httpx

BASE = "http://localhost:8002"
AUTH = {"Authorization": "Bearer arlo-assistant-dev-key"}
PASS = 0
FAIL = 0
ERRORS = []


def api(method: str, path: str, data: dict = None, expect: int = None) -> dict:
    with httpx.Client(base_url=BASE, headers=AUTH, timeout=10) as c:
        if method == "GET":
            r = c.get(path)
        elif method == "POST":
            r = c.post(path, json=data)
        elif method == "PATCH":
            r = c.patch(path, json=data)
        elif method == "DELETE":
            r = c.delete(path)
        else:
            raise ValueError(f"Unknown method: {method}")
    if expect and r.status_code != expect:
        raise AssertionError(f"{method} {path}: expected {expect}, got {r.status_code} — {r.text[:200]}")
    return r.json() if r.status_code < 400 else {"_status": r.status_code, "_detail": r.text[:300]}


def test(name: str, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        ERRORS.append((name, str(e)))
        print(f"  FAIL  {name} — {e}")


def section(name: str):
    print(f"\n{'='*50}\n  {name}\n{'='*50}")


# ─── HEALTH CHECK ───────────────────────────────────────

def test_suite():
    section("HEALTH CHECK")

    def t_health():
        r = api("GET", "/health")
        assert r["status"] == "ok"
    test("GET /health returns ok", t_health)

    # ─── AUTH ───────────────────────────────────────────

    section("AUTH")

    def t_no_token():
        with httpx.Client(base_url=BASE, timeout=5) as c:
            r = c.get("/chat/conversations")
        assert r.status_code in (401, 403)
    test("No token returns 401/403", t_no_token)

    def t_bad_token():
        with httpx.Client(base_url=BASE, headers={"Authorization": "Bearer wrong"}, timeout=5) as c:
            r = c.get("/chat/conversations")
        assert r.status_code == 401
    test("Bad token returns 401", t_bad_token)

    # ─── TASKS ──────────────────────────────────────────

    section("TASKS")

    def t_create_task():
        r = api("POST", "/tasks", {"title": "Test task", "priority": "high", "category": "test"}, expect=201)
        assert r["title"] == "Test task"
        assert r["priority"] == "high"
        assert r["status"] == "todo"
        assert r["completed_at"] is None
        return r["id"]

    task_id = None
    def t_create_task_wrapper():
        nonlocal task_id
        task_id = t_create_task()
    test("POST /tasks creates task", t_create_task_wrapper)

    def t_create_task_defaults():
        r = api("POST", "/tasks", {"title": "Default task"}, expect=201)
        assert r["priority"] == "medium"
        assert r["category"] is None
        api("DELETE", f"/tasks/{r['id']}")
    test("POST /tasks uses defaults", t_create_task_defaults)

    def t_create_task_with_due_date():
        r = api("POST", "/tasks", {"title": "Due task", "due_date": "2026-04-15"}, expect=201)
        assert r["due_date"] == "2026-04-15"
        api("DELETE", f"/tasks/{r['id']}")
    test("POST /tasks with due_date", t_create_task_with_due_date)

    def t_list_tasks():
        r = api("GET", "/tasks")
        assert r["count"] >= 1
        assert any(t["title"] == "Test task" for t in r["tasks"])
    test("GET /tasks lists tasks", t_list_tasks)

    def t_list_tasks_filter_priority():
        r = api("GET", "/tasks?priority=high")
        assert all(t["priority"] == "high" for t in r["tasks"])
    test("GET /tasks?priority=high filters", t_list_tasks_filter_priority)

    def t_list_tasks_filter_status():
        r = api("GET", "/tasks?status=todo")
        assert all(t["status"] == "todo" for t in r["tasks"])
    test("GET /tasks?status=todo filters", t_list_tasks_filter_status)

    def t_update_task():
        r = api("PATCH", f"/tasks/{task_id}", {"title": "Updated task"})
        assert r["title"] == "Updated task"
    test("PATCH /tasks/{id} updates title", t_update_task)

    def t_complete_task():
        r = api("PATCH", f"/tasks/{task_id}", {"status": "done"})
        assert r["status"] == "done"
        assert r["completed_at"] is not None
    test("PATCH /tasks/{id} status=done sets completed_at", t_complete_task)

    def t_update_nonexistent_task():
        r = api("PATCH", "/tasks/00000000-0000-0000-0000-000000000000", {"title": "x"})
        assert r["_status"] == 404
    test("PATCH /tasks/nonexistent returns 404", t_update_nonexistent_task)

    def t_delete_task():
        r = api("DELETE", f"/tasks/{task_id}")
        assert r["deleted"] is True
    test("DELETE /tasks/{id} deletes", t_delete_task)

    def t_delete_nonexistent_task():
        r = api("DELETE", "/tasks/00000000-0000-0000-0000-000000000000")
        assert r["_status"] == 404
    test("DELETE /tasks/nonexistent returns 404", t_delete_nonexistent_task)

    # ─── GOALS ──────────────────────────────────────────

    section("GOALS")

    goal_id = None
    def t_create_goal():
        nonlocal goal_id
        r = api("POST", "/goals", {"title": "Bench 225", "target_value": 225, "unit": "lbs", "category": "fitness"}, expect=201)
        assert r["title"] == "Bench 225"
        assert r["current_value"] == 0
        assert r["status"] == "active"
        goal_id = r["id"]
    test("POST /goals creates goal", t_create_goal)

    def t_list_goals():
        r = api("GET", "/goals")
        assert r["count"] >= 1
    test("GET /goals lists goals", t_list_goals)

    def t_filter_goals_category():
        r = api("GET", "/goals?category=fitness")
        assert all(g["category"] == "fitness" for g in r["goals"])
    test("GET /goals?category=fitness filters", t_filter_goals_category)

    def t_update_goal_progress():
        r = api("PATCH", f"/goals/{goal_id}", {"current_value": 185})
        assert r["current_value"] == 185
        assert r["status"] == "active"
    test("PATCH /goals/{id} updates progress", t_update_goal_progress)

    def t_goal_auto_achieved():
        r = api("PATCH", f"/goals/{goal_id}", {"current_value": 230})
        assert r["current_value"] == 230
        assert r["status"] == "achieved"
    test("PATCH /goals/{id} auto-achieves when target met", t_goal_auto_achieved)

    def t_delete_goal():
        r = api("DELETE", f"/goals/{goal_id}")
        assert r["deleted"] is True
    test("DELETE /goals/{id} deletes", t_delete_goal)

    # ─── HABITS ─────────────────────────────────────────

    section("HABITS")

    habit_id = None
    def t_create_habit():
        nonlocal habit_id
        r = api("POST", "/habits", {"name": "Meditate", "frequency": "daily"}, expect=201)
        assert r["name"] == "Meditate"
        assert r["current_streak"] == 0
        assert r["best_streak"] == 0
        assert r["last_done"] is None
        habit_id = r["id"]
    test("POST /habits creates habit", t_create_habit)

    def t_check_habit_first():
        r = api("PATCH", f"/habits/{habit_id}/check")
        assert r["current_streak"] == 1
        assert r["best_streak"] == 1
        assert r["last_done"] is not None
    test("PATCH /habits/{id}/check first check-in", t_check_habit_first)

    def t_check_habit_duplicate():
        r = api("PATCH", f"/habits/{habit_id}/check")
        assert r["current_streak"] == 1  # same day, no change
    test("PATCH /habits/{id}/check same day = no change", t_check_habit_duplicate)

    def t_list_habits():
        r = api("GET", "/habits")
        assert r["count"] >= 1
        assert any(h["name"] == "Meditate" for h in r["habits"])
    test("GET /habits lists habits", t_list_habits)

    def t_check_nonexistent_habit():
        r = api("PATCH", "/habits/00000000-0000-0000-0000-000000000000/check")
        assert r["_status"] == 404
    test("PATCH /habits/nonexistent/check returns 404", t_check_nonexistent_habit)

    def t_delete_habit():
        r = api("DELETE", f"/habits/{habit_id}")
        assert r["deleted"] is True
    test("DELETE /habits/{id} deletes", t_delete_habit)

    # ─── RECIPES ────────────────────────────────────────

    section("RECIPES")

    recipe_id = None
    def t_create_recipe():
        nonlocal recipe_id
        r = api("POST", "/recipes", {
            "name": "Chicken Stir Fry",
            "ingredients": [{"item": "chicken", "amount": "1 lb"}],
            "instructions": "Cook it.",
            "calories": 450, "protein_g": 42,
            "prep_time_minutes": 20,
            "tags": ["high-protein", "quick"],
        }, expect=201)
        assert r["name"] == "Chicken Stir Fry"
        assert r["tags"] == ["high-protein", "quick"]
        recipe_id = r["id"]
    test("POST /recipes creates recipe", t_create_recipe)

    def t_get_recipe():
        r = api("GET", f"/recipes/{recipe_id}")
        assert r["name"] == "Chicken Stir Fry"
        assert r["ingredients"][0]["item"] == "chicken"
    test("GET /recipes/{id} returns recipe", t_get_recipe)

    def t_list_recipes():
        r = api("GET", "/recipes")
        assert r["count"] >= 1
    test("GET /recipes lists recipes", t_list_recipes)

    def t_search_recipes():
        r = api("GET", "/recipes?search=chicken")
        assert r["count"] >= 1
        assert all("chicken" in rec["name"].lower() for rec in r["recipes"])
    test("GET /recipes?search=chicken filters", t_search_recipes)

    def t_search_recipes_no_match():
        r = api("GET", "/recipes?search=xyznonexistent")
        assert r["count"] == 0
    test("GET /recipes?search=nomatch returns empty", t_search_recipes_no_match)

    def t_get_nonexistent_recipe():
        r = api("GET", "/recipes/00000000-0000-0000-0000-000000000000")
        assert r["_status"] == 404
    test("GET /recipes/nonexistent returns 404", t_get_nonexistent_recipe)

    def t_delete_recipe():
        r = api("DELETE", f"/recipes/{recipe_id}")
        assert r["deleted"] is True
    test("DELETE /recipes/{id} deletes", t_delete_recipe)

    # ─── GROCERY LISTS ──────────────────────────────────

    section("GROCERY LISTS")

    gl_id = None
    def t_create_grocery_list():
        nonlocal gl_id
        r = api("POST", "/grocery-lists", {
            "name": "Weekly Shop",
            "items": [
                {"item": "eggs", "section": "dairy", "checked": False},
                {"item": "chicken", "section": "meat", "checked": False},
            ]
        }, expect=201)
        assert r["name"] == "Weekly Shop"
        assert len(r["items"]) == 2
        gl_id = r["id"]
    test("POST /grocery-lists creates list", t_create_grocery_list)

    def t_toggle_item_on():
        r = api("PATCH", f"/grocery-lists/{gl_id}/items/0/check")
        assert r["items"][0]["checked"] is True
        assert r["items"][1]["checked"] is False
    test("PATCH toggle item 0 → checked=True", t_toggle_item_on)

    def t_toggle_item_off():
        r = api("PATCH", f"/grocery-lists/{gl_id}/items/0/check")
        assert r["items"][0]["checked"] is False
    test("PATCH toggle item 0 back → checked=False", t_toggle_item_off)

    def t_toggle_invalid_index():
        r = api("PATCH", f"/grocery-lists/{gl_id}/items/99/check")
        assert r["_status"] == 404
    test("PATCH toggle invalid index returns 404", t_toggle_invalid_index)

    def t_get_grocery_list():
        r = api("GET", f"/grocery-lists/{gl_id}")
        assert r["name"] == "Weekly Shop"
    test("GET /grocery-lists/{id} returns list", t_get_grocery_list)

    def t_list_grocery_lists():
        r = api("GET", "/grocery-lists")
        assert r["count"] >= 1
    test("GET /grocery-lists lists all", t_list_grocery_lists)

    def t_delete_grocery_list():
        r = api("DELETE", f"/grocery-lists/{gl_id}")
        assert r["deleted"] is True
    test("DELETE /grocery-lists/{id} deletes", t_delete_grocery_list)

    # ─── KNOWLEDGE ──────────────────────────────────────

    section("KNOWLEDGE")

    def t_knowledge_empty():
        r = api("GET", "/knowledge")
        # May or may not be empty depending on prior test runs
        assert "entries" in r
        assert "count" in r
    test("GET /knowledge returns list", t_knowledge_empty)

    def t_knowledge_filter_category():
        r = api("GET", "/knowledge?category=nonexistent")
        assert r["count"] == 0
    test("GET /knowledge?category=nonexistent returns empty", t_knowledge_filter_category)

    def t_knowledge_get_nonexistent():
        r = api("GET", "/knowledge/00000000-0000-0000-0000-000000000000")
        assert r["_status"] == 404
    test("GET /knowledge/nonexistent returns 404", t_knowledge_get_nonexistent)

    # ─── REMINDERS ──────────────────────────────────────

    section("REMINDERS")

    reminder_id = None
    def t_create_time_reminder():
        nonlocal reminder_id
        r = api("POST", "/reminders", {
            "message": "Take vitamins",
            "remind_at": "2020-01-01T08:00:00Z",  # past = should trigger
        }, expect=201)
        assert r["message"] == "Take vitamins"
        assert r["status"] == "active"
        reminder_id = r["id"]
    test("POST /reminders creates time-based reminder", t_create_time_reminder)

    smart_id = None
    def t_create_smart_reminder():
        nonlocal smart_id
        r = api("POST", "/reminders", {
            "message": "Go walk",
            "smart_condition": {"type": "steps_below", "threshold": 99999, "after_hour": 0},
        }, expect=201)
        assert r["smart_condition"]["type"] == "steps_below"
        smart_id = r["id"]
    test("POST /reminders creates smart condition reminder", t_create_smart_reminder)

    def t_list_reminders():
        r = api("GET", "/reminders")
        assert r["count"] >= 2
    test("GET /reminders lists all", t_list_reminders)

    def t_list_active_reminders():
        r = api("GET", "/reminders?status=active")
        assert all(rem["status"] == "active" for rem in r["reminders"])
    test("GET /reminders?status=active filters", t_list_active_reminders)

    def t_triggered_reminders():
        r = api("GET", "/reminders/triggered")
        assert r["count"] >= 1  # time-based in past should trigger
        msgs = [rem["message"] for rem in r["reminders"]]
        assert "Take vitamins" in msgs
    test("GET /reminders/triggered includes past-due", t_triggered_reminders)

    def t_dismiss_reminder():
        r = api("PATCH", f"/reminders/{reminder_id}/dismiss")
        assert r["status"] == "dismissed"
    test("PATCH /reminders/{id}/dismiss works", t_dismiss_reminder)

    def t_dismiss_nonexistent():
        r = api("PATCH", "/reminders/00000000-0000-0000-0000-000000000000/dismiss")
        assert r["_status"] == 404
    test("PATCH /reminders/nonexistent/dismiss returns 404", t_dismiss_nonexistent)

    def t_delete_reminders():
        api("DELETE", f"/reminders/{reminder_id}")
        api("DELETE", f"/reminders/{smart_id}")
    test("DELETE /reminders cleanup", t_delete_reminders)

    # ─── HEALTH TRACKING ────────────────────────────────

    section("HEALTH TRACKING")

    def t_log_steps():
        r = api("POST", "/health/steps", {"steps": 5000})
        assert r["steps"] == 5000
    test("POST /health/steps logs steps", t_log_steps)

    def t_update_steps():
        r = api("POST", "/health/steps", {"steps": 12000})
        assert r["steps"] == 12000
    test("POST /health/steps updates same day", t_update_steps)

    def t_log_meal():
        r = api("POST", "/health/meals", {
            "description": "Test meal",
            "calories": 500, "protein_g": 40,
            "carbs_g": 50, "fat_g": 20,
            "meal_type": "lunch",
        })
        assert r["description"] == "Test meal"
        assert r["calories"] == 500
    test("POST /health/meals logs meal with macros", t_log_meal)

    def t_list_meals():
        r = api("GET", "/health/meals")
        assert r["count"] >= 1
    test("GET /health/meals lists meals", t_list_meals)

    def t_log_workout():
        r = api("POST", "/health/workouts", {
            "workout_type": "running",
            "duration_minutes": 30,
            "notes": "Easy 5k",
        })
        assert r["type"] == "running"
        assert r["duration_minutes"] == 30
    test("POST /health/workouts logs workout", t_log_workout)

    def t_dashboard():
        r = api("GET", "/health/dashboard")
        assert r["steps"] == 12000
        assert r["meals_logged"] >= 1
        assert r["workouts_logged"] >= 1
    test("GET /health/dashboard aggregates correctly", t_dashboard)

    def t_weekly():
        r = api("GET", "/health/weekly")
        assert r["days_logged"] >= 1
        assert "averages" in r
    test("GET /health/weekly returns summary", t_weekly)

    # ─── CHAT ───────────────────────────────────────────

    section("CHAT")

    msg_id = None
    conv_id = None
    def t_send_message():
        nonlocal msg_id, conv_id
        r = api("POST", "/chat/message", {"text": "Test message from full API test"})
        assert r["status"] == "thinking"
        assert r["message_id"] is not None
        msg_id = r["message_id"]
        conv_id = r["conversation_id"]
    test("POST /chat/message returns thinking", t_send_message)

    def t_get_message():
        r = api("GET", f"/chat/message/{msg_id}")
        assert r["message_id"] == msg_id
    test("GET /chat/message/{id} returns message", t_get_message)

    def t_list_conversations():
        r = api("GET", "/chat/conversations")
        assert r["count"] >= 1
    test("GET /chat/conversations lists threads", t_list_conversations)

    def t_get_conversation():
        r = api("GET", f"/chat/conversations/{conv_id}")
        assert len(r["messages"]) >= 1
    test("GET /chat/conversations/{id} returns messages", t_get_conversation)

    def t_get_nonexistent_message():
        r = api("GET", "/chat/message/00000000-0000-0000-0000-000000000000")
        assert r["_status"] == 404
    test("GET /chat/message/nonexistent returns 404", t_get_nonexistent_message)


# ─── RUN ────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  ARLO ASSISTANT — FULL API TEST SUITE")
    print("="*50)

    try:
        api("GET", "/health")
    except Exception:
        print("\nERROR: Cannot reach http://localhost:8002")
        print("Run: docker compose up -d")
        sys.exit(1)

    test_suite()

    print(f"\n{'='*50}")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")

    if ERRORS:
        print("\nFailed tests:")
        for name, err in ERRORS:
            print(f"  {name}: {err}")

    sys.exit(1 if FAIL > 0 else 0)
