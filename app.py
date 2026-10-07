"""CROPY: Crop Recommendation & Management Planning System (Flask app)."""
import json
import os
from datetime import date, datetime, timedelta

import joblib
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from utils import database as db
from utils import management as mgmt
from utils import weather as wx
from utils.preprocessing import SEASONS, to_frame
from utils.validation import validate_coordinates, validate_prediction_input, validate_sowing_date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "crop_model.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "model", "metrics.json")


def load_env(path=os.path.join(BASE_DIR, ".env")):
    """Minimal .env loader (KEY=VALUE lines); real environment variables win."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

CITIES = [
    ("Dehradun", 30.3165, 78.0322), ("Delhi", 28.6139, 77.2090), ("Mumbai", 19.0760, 72.8777), ("Kolkata", 22.5726, 88.3639),
    ("Chennai", 13.0827, 80.2707), ("Bengaluru", 12.9716, 77.5946), ("Hyderabad", 17.3850, 78.4867),
    ("Pune", 18.5204, 73.8567), ("Ahmedabad", 23.0225, 72.5714), ("Jaipur", 26.9124, 75.7873),
    ("Lucknow", 26.8467, 80.9462), ("Bhopal", 23.2599, 77.4126), ("Patna", 25.5941, 85.1376),
    ("Ludhiana", 30.9010, 75.8573), ("Nagpur", 21.1458, 79.0882), ("Indore", 22.7196, 75.8577),
    ("Coimbatore", 11.0168, 76.9558),
]
DEFAULT_LOCATION = {"name": "Dehradun", "lat": 30.3165, "lon": 78.0322}

MODEL = None
METRICS = None


def load_model():
    global MODEL, METRICS
    try:
        MODEL = joblib.load(MODEL_PATH)
        mgmt.validate_management(MODEL.classes_)
    except FileNotFoundError:
        MODEL = None
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            METRICS = json.load(f)


db.init_db()
load_model()


# ------------------------------------------------------------------ helpers
def today():
    return date.today()


def fmt_date(value, pattern="%d %b %Y"):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime(pattern)


app.jinja_env.filters["fdate"] = fmt_date
app.jinja_env.filters["fshort"] = lambda v: fmt_date(v, "%d %b")


def due_text(status, days_until):
    if status == "Completed":
        return "Completed"
    if status == "Due Today":
        return "Due today"
    if status == "Overdue":
        n = abs(days_until)
        return f"Overdue by {n} day{'s' if n != 1 else ''}"
    return f"Due in {days_until} day{'s' if days_until != 1 else ''}"


def enrich_tasks(rows):
    t0 = today()
    out = []
    for r in rows:
        done = r["status"] == "completed"
        st = mgmt.task_status(r["task_date"], done, t0)
        days = (mgmt.parse_date(r["task_date"]) - t0).days
        out.append({
            "id": r["id"], "plan_id": r["plan_id"], "task_day": r["task_day"], "task_date": r["task_date"],
            "activity": r["activity"], "description": r["description"], "category": r["category"],
            "completed": done, "completed_at": r["completed_at"], "status": st, "days_until": days,
            "due_text": due_text(st, days),
        })
    return out


def schedule_alerts(tasks):
    """Alerts derived purely from the stored schedule (no weather needed)."""
    alerts = []
    due = [t for t in tasks if t["status"] == "Due Today"]
    overdue = [t for t in tasks if t["status"] == "Overdue"]
    for t in due[:4]:
        alerts.append({"level": "warning", "title": "Due today", "source": "Crop schedule",
                       "message": f"{t['activity']} is due today."})
    if overdue:
        worst = max(-t["days_until"] for t in overdue)
        names = ", ".join(sorted({t["activity"] for t in overdue})[:3])
        more = f" and {len(overdue) - 3} more" if len({t['activity'] for t in overdue}) > 3 else ""
        alerts.append({"level": "high" if worst > 7 else "warning", "title": "Overdue tasks",
                       "source": "Crop schedule",
                       "message": f"{len(overdue)} task{'s are' if len(overdue) != 1 else ' is'} overdue: {names}{more}."})
    harvest = [t for t in tasks if t["activity"] == "Harvest" and not t["completed"] and 0 < t["days_until"] <= 7]
    for t in harvest:
        alerts.append({"level": "info", "title": "Harvest window", "source": "Crop schedule",
                       "message": f"Harvest window begins in {t['days_until']} day{'s' if t['days_until'] != 1 else ''}."})
    return alerts


def predict(values):
    """Run the saved pipeline. Returns (crop, confidence_percent, top3 list)."""
    frame = to_frame(values["humidity"], values["rainfall"], values["season"], values["land_area"])
    proba = MODEL.predict_proba(frame)[0]
    order = proba.argsort()[::-1]
    classes = MODEL.classes_
    top = [{"crop": str(classes[i]), "confidence": round(float(proba[i]) * 100, 1)} for i in order[:3]]
    return top[0]["crop"], float(proba[order[0]]) * 100, top


def plan_context(plan_id):
    plan = db.get_plan(plan_id)
    if plan is None:
        return None
    tasks = enrich_tasks(db.plan_tasks(plan_id))
    return plan, tasks


def counts(tasks):
    return {
        "due": sum(1 for t in tasks if t["status"] == "Due Today"),
        "overdue": sum(1 for t in tasks if t["status"] == "Overdue"),
        "upcoming": sum(1 for t in tasks if t["status"] == "Upcoming"),
        "completed": sum(1 for t in tasks if t["status"] == "Completed"),
        "total": len(tasks),
    }


@app.context_processor
def inject_globals():
    return {"cities": CITIES, "default_location": DEFAULT_LOCATION,
            "model_ready": MODEL is not None}


# ------------------------------------------------------------------- pages
@app.route("/")
def dashboard():
    plan = db.latest_plan()
    tasks, crop_info = [], None
    if plan:
        tasks = enrich_tasks(db.plan_tasks(plan["id"]))
        crop_info = mgmt.get_crop(plan["crop"])
    c = counts(tasks)
    todays = [t for t in tasks if t["status"] in ("Due Today", "Overdue")][:5]
    next_task = next((t for t in tasks if t["status"] == "Upcoming"), None)
    recent = db.list_predictions(1)
    progress = None
    if plan and crop_info:
        elapsed = (today() - mgmt.parse_date(plan["sowing_date"])).days
        progress = {"day": max(elapsed, 0), "total": crop_info["duration_days"],
                    "pct": max(0, min(100, round(elapsed / crop_info["duration_days"] * 100))),
                    "not_started": elapsed < 0, "days_to_start": -elapsed}
    return render_template(
        "dashboard.html", plan=plan, counts=c, todays=todays, next_task=next_task,
        recent=recent[0] if recent else None, progress=progress, alerts=schedule_alerts(tasks),
    )


@app.route("/recommend", methods=["GET", "POST"])
def recommend():
    if request.method == "GET":
        return render_template("recommend.html", values={"humidity": 75, "rainfall": 180, "season": "Kharif", "land_area": 2.0},
                               errors={})
    if MODEL is None:
        return render_template("recommend.html", values=request.form, errors={},
                               form_error="The model has not been trained yet. Run python train_model.py."), 503
    values, errors = validate_prediction_input(request.form)
    if errors:
        return render_template("recommend.html", values=request.form, errors=errors), 400
    try:
        crop, conf, _ = predict(values)
    except Exception:
        app.logger.exception("prediction failed")
        return render_template("recommend.html", values=request.form, errors={},
                               form_error="Something went wrong while analyzing the conditions. Please try again."), 500
    pid = db.add_prediction(values["humidity"], values["rainfall"], values["season"], values["land_area"],
                            crop, round(conf, 1))
    return redirect(url_for("result", pid=pid))


@app.route("/result/<int:pid>")
def result(pid):
    row = db.get_prediction(pid)
    if row is None:
        abort(404)
    top = []
    if MODEL is not None:
        try:
            _, _, top = predict({"humidity": row["humidity"], "rainfall": row["rainfall"],
                                 "season": row["season"], "land_area": row["land_area"]})
        except Exception:
            top = []
    info = mgmt.get_crop(row["predicted_crop"])
    plan = db.get_plan(row["plan_id"]) if row["plan_id"] else None
    return render_template("result.html", p=row, top=top[1:], info=info, plan=plan, today=today().isoformat())


@app.route("/result/<int:pid>/plan", methods=["GET", "POST"])
def start_plan(pid):
    if request.method == "GET":
        return redirect(url_for("result", pid=pid))

    row = db.get_prediction(pid)
    if row is None:
        abort(404)
    if row["plan_id"]:
        return redirect(url_for("crop_plan", plan_id=row["plan_id"]))
    if request.form.get("start_today"):
        sowing = today()
    else:
        sowing, err = validate_sowing_date(request.form.get("sowing_date"), today())
        if err:
            info = mgmt.get_crop(row["predicted_crop"])
            return render_template("result.html", p=row, top=[], info=info, plan=None,
                                   today=today().isoformat(), plan_error=err), 400
    schedule = mgmt.build_schedule(row["predicted_crop"], sowing)
    plan_id = db.create_plan(row["predicted_crop"], sowing.isoformat(), schedule, history_id=pid)
    return redirect(url_for("crop_plan", plan_id=plan_id))


@app.route("/plan")
@app.route("/plan/<int:plan_id>")
def crop_plan(plan_id=None):
    plan = db.get_plan(plan_id) if plan_id else db.latest_plan()
    if plan_id and plan is None:
        abort(404)
    if plan is None:
        return render_template("crop_plan.html", plan=None, crop=None, info=None, tasks=[], stages=[], counts=None)
    info = mgmt.get_crop(plan["crop"])
    tasks = enrich_tasks(db.plan_tasks(plan["id"]))
    end = mgmt.parse_date(plan["sowing_date"]) + timedelta(days=info["duration_days"])
    return render_template("crop_plan.html", plan=plan, crop=plan["crop"], info=info, tasks=tasks,
                           stages=mgmt.lifecycle(plan["crop"], plan["sowing_date"]), counts=counts(tasks),
                           harvest_date=end.isoformat(), alerts=schedule_alerts(tasks))


@app.route("/crop/<crop>")
def crop_preview(crop):
    info = mgmt.get_crop(crop)
    if info is None:
        abort(404)
    return render_template("crop_plan.html", plan=None, crop=crop, info=info, tasks=[],
                           stages=mgmt.lifecycle(crop), counts=None, preview=True)


@app.route("/schedule")
def schedule():
    plans = db.list_plans()
    plan_id = request.args.get("plan", type=int)
    plan = db.get_plan(plan_id) if plan_id else (plans[0] if plans else None)
    if plan_id and plan is None:
        abort(404)
    tasks = enrich_tasks(db.plan_tasks(plan["id"])) if plan else []
    return render_template("schedule.html", plan=plan, plans=plans, tasks=tasks, counts=counts(tasks),
                           alerts=schedule_alerts(tasks))


@app.route("/history")
def history():
    return render_template("history.html", rows=db.list_predictions())



# --------------------------------------------------------------------- API
@app.route("/api/weather")
def api_weather():
    coords = validate_coordinates(request.args.get("lat"), request.args.get("lon"))
    if coords is None:
        return jsonify({"available": False, "error": "A valid location is required to load weather.",
                        "current": None, "hourly": [], "daily": [], "alerts": [], "advisories": []}), 400
    try:
        data = wx.get_weather(coords[0], coords[1], refresh=request.args.get("refresh") == "1")
        plan_id = request.args.get("plan", type=int)
        plan = db.get_plan(plan_id) if plan_id else db.latest_plan()
        tasks = enrich_tasks(db.plan_tasks(plan["id"])) if plan else []
        data["advisories"] = wx.weather_advisories(data, tasks)
        for a in data["alerts"]:
            a["level"] = wx.official_alert_level(a)
        return jsonify(data)
    except Exception as exc:
        app.logger.exception("Weather API route failed")
        return jsonify({
            "available": False,
            "error": "Weather backend error: " + str(exc),
            "current": None, "hourly": [], "daily": [], "alerts": [], "advisories": []
        }), 500


@app.route("/api/tasks/<int:task_id>/toggle", methods=["POST"])
def api_toggle_task(task_id):
    if db.get_task(task_id) is None:
        return jsonify({"ok": False, "error": "Task not found."}), 404
    body = request.get_json(silent=True) or {}
    completed = bool(body.get("completed", True))
    row = db.set_task_completed(task_id, completed)
    tasks = enrich_tasks(db.plan_tasks(row["plan_id"]))
    this = next(t for t in tasks if t["id"] == task_id)
    return jsonify({"ok": True, "task": this, "counts": counts(tasks)})


# ---------------------------------------------------------------- errors
@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", title="Page not found",
                           message="We could not find what you were looking for."), 404


@app.errorhandler(500)
def server_error(_):
    return render_template("error.html", title="Something went wrong",
                           message="An unexpected problem occurred. Your saved data is safe."), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
