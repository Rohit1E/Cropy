"""Crop management data access, CSV/JSON consistency check and schedule maths."""
import json
import os
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANAGEMENT_PATH = os.path.join(BASE_DIR, "data", "crop_management.json")
DATASET_PATH = os.path.join(BASE_DIR, "data", "crop_dataset.csv")

REQUIRED_KEYS = [
    "overview", "conditions", "fertilizer", "npk", "fertilizer_quantity", "irrigation",
    "duration_days", "growth_stages", "tasks", "pest_monitoring", "harvest",
]

_cache = None


def load_management(force=False):
    global _cache
    if _cache is None or force:
        with open(MANAGEMENT_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def get_crop(crop):
    return load_management().get(crop)


def validate_management(dataset_crops):
    """Raise ValueError unless CSV crops == management crops and entries are complete."""
    mgmt = load_management()
    csv_set, mgmt_set = set(dataset_crops), set(mgmt)
    if csv_set != mgmt_set:
        raise ValueError(
            f"Crop mismatch. In dataset only: {sorted(csv_set - mgmt_set)}; "
            f"in management only: {sorted(mgmt_set - csv_set)}"
        )
    for crop, entry in mgmt.items():
        missing = [k for k in REQUIRED_KEYS if k not in entry]
        if missing:
            raise ValueError(f"{crop}: management entry missing {missing}")
        if not entry["tasks"] or not entry["growth_stages"]:
            raise ValueError(f"{crop}: empty tasks or growth stages")
        if any(not 0 <= t["day"] <= entry["duration_days"] for t in entry["tasks"]):
            raise ValueError(f"{crop}: a task day falls outside the crop duration")
    return True


def parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_schedule(crop, sowing_date):
    """Tasks for a crop with real calendar dates computed from the sowing date."""
    entry = get_crop(crop)
    if entry is None:
        raise KeyError(crop)
    start = parse_date(sowing_date)
    out = []
    for t in entry["tasks"]:
        out.append({
            "task_day": t["day"],
            "task_date": (start + timedelta(days=t["day"])).isoformat(),
            "activity": t["activity"],
            "description": t["description"],
            "category": t["category"],
        })
    return out


def lifecycle(crop, sowing_date=None):
    entry = get_crop(crop)
    start = parse_date(sowing_date) if sowing_date else None
    stages = []
    for s in entry["growth_stages"]:
        item = dict(s)
        if start:
            item["date"] = (start + timedelta(days=s["day"])).isoformat()
        stages.append(item)
    return stages


def task_status(task_date, completed, today=None):
    """Upcoming / Due Today / Completed / Overdue."""
    if completed:
        return "Completed"
    today = today or date.today()
    d = parse_date(task_date)
    if d < today:
        return "Overdue"
    if d == today:
        return "Due Today"
    return "Upcoming"
