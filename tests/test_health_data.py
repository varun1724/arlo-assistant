import pytest
from datetime import date


@pytest.mark.asyncio
async def test_log_steps(client):
    r = await client.post("/health/steps", json={"steps": 8500})
    assert r.status_code == 200
    data = r.json()
    assert data["steps"] == 8500
    assert data["date"] == date.today().isoformat()


@pytest.mark.asyncio
async def test_log_steps_updates_existing(client):
    """Logging steps twice should update, not add."""
    await client.post("/health/steps", json={"steps": 5000})
    r = await client.post("/health/steps", json={"steps": 8000})
    assert r.json()["steps"] == 8000


@pytest.mark.asyncio
async def test_log_steps_specific_date(client):
    r = await client.post("/health/steps", json={"steps": 10000, "date": "2026-03-15"})
    assert r.json()["date"] == "2026-03-15"
    assert r.json()["steps"] == 10000


@pytest.mark.asyncio
async def test_log_meal(client):
    r = await client.post("/health/meals", json={
        "description": "3 eggs and toast",
        "calories": 350,
        "protein_g": 25,
        "carbs_g": 30,
        "fat_g": 18,
        "meal_type": "breakfast",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["description"] == "3 eggs and toast"
    assert data["protein_g"] == 25
    assert data["calories"] == 350
    assert "id" in data


@pytest.mark.asyncio
async def test_log_meal_empty_description_rejected(client):
    r = await client.post("/health/meals", json={
        "description": "",
        "calories": 100,
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_meals(client):
    # Log a meal first
    await client.post("/health/meals", json={
        "description": "Chicken salad",
        "calories": 400,
        "protein_g": 40,
    })

    r = await client.get("/health/meals")
    assert r.status_code == 200
    assert r.json()["count"] >= 1
    assert r.json()["meals"][0]["description"] is not None


@pytest.mark.asyncio
async def test_log_workout(client):
    r = await client.post("/health/workouts", json={
        "workout_type": "chest and back",
        "duration_minutes": 60,
        "exercises": [
            {"name": "bench press", "sets": 3, "reps": 10},
            {"name": "pull ups", "sets": 3, "reps": 8},
        ],
        "notes": "Felt strong today",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "chest and back"
    assert data["duration_minutes"] == 60


@pytest.mark.asyncio
async def test_log_workout_empty_type_rejected(client):
    r = await client.post("/health/workouts", json={"workout_type": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_dashboard(client):
    # Log some data first
    await client.post("/health/steps", json={"steps": 7500})
    await client.post("/health/meals", json={
        "description": "Protein shake",
        "calories": 200,
        "protein_g": 40,
    })

    r = await client.get("/health/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert data["date"] == date.today().isoformat()
    assert data["steps"] == 7500
    assert data["protein_g"] >= 40
    assert data["meals_logged"] >= 1


@pytest.mark.asyncio
async def test_dashboard_macros_sum_from_meals(client):
    """Daily macros should be the sum of all meals logged today."""
    await client.post("/health/meals", json={
        "description": "Eggs",
        "calories": 200,
        "protein_g": 18,
        "carbs_g": 2,
        "fat_g": 14,
    })
    await client.post("/health/meals", json={
        "description": "Chicken",
        "calories": 300,
        "protein_g": 45,
        "carbs_g": 0,
        "fat_g": 8,
    })

    r = await client.get("/health/dashboard")
    data = r.json()
    # Should be at least the sum of these two meals (may have others from prior tests)
    assert data["protein_g"] >= 63
    assert data["calories"] >= 500


@pytest.mark.asyncio
async def test_weekly_summary(client):
    r = await client.get("/health/weekly")
    assert r.status_code == 200
    data = r.json()
    assert "period" in data
    assert "averages" in data
    assert "daily" in data
    assert "workouts" in data
