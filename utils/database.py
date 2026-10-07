"""SQLite persistence: prediction_history, farm_plans, farm_tasks (parameterized SQL only)."""
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("CROPY_DB_PATH") or os.path.join(BASE_DIR, "database", "cropy.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS prediction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    humidity REAL NOT NULL,
    rainfall REAL NOT NULL,
    season TEXT NOT NULL,
    land_area REAL NOT NULL,
    predicted_crop TEXT NOT NULL,
    confidence REAL NOT NULL,
    sowing_date TEXT,
    plan_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS farm_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crop TEXT NOT NULL,
    sowing_date TEXT NOT NULL,
    history_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS farm_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES farm_plans(id) ON DELETE CASCADE,
    task_day INTEGER NOT NULL,
    task_date TEXT NOT NULL,
    activity TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_plan ON farm_tasks(plan_id, task_day);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- predictions
def add_prediction(humidity, rainfall, season, land_area, crop, confidence):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO prediction_history (humidity, rainfall, season, land_area, predicted_crop, confidence, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (humidity, rainfall, season, land_area, crop, confidence, _now()),
        )
        return cur.lastrowid


def get_prediction(pid):
    with connect() as conn:
        return conn.execute("SELECT * FROM prediction_history WHERE id = ?", (pid,)).fetchone()


def list_predictions(limit=200):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM prediction_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


# ---------------------------------------------------------------------- plans
def create_plan(crop, sowing_date, schedule, history_id=None):
    """Create a plan and its tasks in one transaction; link it to the prediction."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO farm_plans (crop, sowing_date, history_id, created_at) VALUES (?, ?, ?, ?)",
            (crop, sowing_date, history_id, _now()),
        )
        plan_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO farm_tasks (plan_id, task_day, task_date, activity, description, category) VALUES (?, ?, ?, ?, ?, ?)",
            [(plan_id, t["task_day"], t["task_date"], t["activity"], t["description"], t["category"]) for t in schedule],
        )
        if history_id is not None:
            conn.execute(
                "UPDATE prediction_history SET sowing_date = ?, plan_id = ? WHERE id = ?",
                (sowing_date, plan_id, history_id),
            )
        return plan_id


def get_plan(plan_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM farm_plans WHERE id = ?", (plan_id,)).fetchone()


def latest_plan():
    with connect() as conn:
        return conn.execute("SELECT * FROM farm_plans ORDER BY id DESC LIMIT 1").fetchone()


def list_plans():
    with connect() as conn:
        return conn.execute("SELECT * FROM farm_plans ORDER BY id DESC").fetchall()


def plan_tasks(plan_id):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM farm_tasks WHERE plan_id = ? ORDER BY task_day, id", (plan_id,)
        ).fetchall()


def get_task(task_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM farm_tasks WHERE id = ?", (task_id,)).fetchone()


def set_task_completed(task_id, completed):
    with connect() as conn:
        if completed:
            conn.execute(
                "UPDATE farm_tasks SET status = 'completed', completed_at = ? WHERE id = ?",
                (_now(), task_id),
            )
        else:
            conn.execute(
                "UPDATE farm_tasks SET status = 'pending', completed_at = NULL WHERE id = ?",
                (task_id,),
            )
        return conn.execute("SELECT * FROM farm_tasks WHERE id = ?", (task_id,)).fetchone()
