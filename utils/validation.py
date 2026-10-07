"""Input validation for the recommendation form and sowing dates."""
from datetime import date, timedelta

from utils.preprocessing import SEASONS

LIMITS = {
    "humidity": (0.0, 100.0),
    "rainfall": (0.0, 1000.0),
    "land_area": (0.1, 1000.0),
}


def _num(raw):
    if raw is None:
        return None
    raw = str(raw).strip()
    if raw == "":
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def validate_prediction_input(form):
    """Return (clean_values, errors). errors maps field name -> message."""
    errors, clean = {}, {}

    h = _num(form.get("humidity"))
    if h is None or not LIMITS["humidity"][0] <= h <= LIMITS["humidity"][1]:
        errors["humidity"] = "Please enter a valid humidity between 0 and 100 %."
    else:
        clean["humidity"] = h

    r = _num(form.get("rainfall"))
    if r is None or not LIMITS["rainfall"][0] <= r <= LIMITS["rainfall"][1]:
        errors["rainfall"] = "Please enter a valid rainfall value between 0 and 1000 mm."
    else:
        clean["rainfall"] = r

    season = (form.get("season") or "").strip()
    if season not in SEASONS:
        errors["season"] = "Please choose Kharif, Rabi or Zaid."
    else:
        clean["season"] = season

    a = _num(form.get("land_area"))
    if a is None or not LIMITS["land_area"][0] <= a <= LIMITS["land_area"][1]:
        errors["land_area"] = "Please enter a valid land area between 0.1 and 1000 acres."
    else:
        clean["land_area"] = a

    return clean, errors


def validate_sowing_date(raw, today=None):
    """Return (date, error). Accepts YYYY-MM-DD within one year of today."""
    today = today or date.today()
    try:
        d = date.fromisoformat((raw or "").strip())
    except ValueError:
        return None, "Please choose a valid sowing date."
    if d < today - timedelta(days=365) or d > today + timedelta(days=365):
        return None, "Sowing date must be within one year of today."
    return d, None


def validate_coordinates(lat, lon):
    la, lo = _num(lat), _num(lon)
    if la is None or lo is None or not -90 <= la <= 90 or not -180 <= lo <= 180:
        return None
    return la, lo
