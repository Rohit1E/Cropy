import os
import sys
import tempfile
from datetime import date, timedelta

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CROPY_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("GOOGLE_MAPS_API_KEY", None)

import app as cropy  # noqa: E402
from utils import management as mgmt  # noqa: E402
from utils import weather as wx  # noqa: E402

SECRET = "TEST-SECRET-KEY-123"


@pytest.fixture(scope="module")
def client():
    cropy.app.config["TESTING"] = True
    return cropy.app.test_client()


# ---------------------------------------------------------------- dataset
def test_dataset():
    df = pd.read_csv(os.path.join(ROOT, "data", "crop_dataset.csv"))
    assert list(df.columns) == ["humidity", "rainfall", "season", "land_area", "crop"]
    assert df.crop.nunique() == 30
    assert 600 <= len(df) <= 900
    assert not df.duplicated().any()
    assert df.humidity.between(0, 100).all() and (df.rainfall >= 0).all() and (df.land_area > 0).all()
    counts = df.crop.value_counts()
    assert counts.min() >= 20 and counts.max() <= 30
    assert set(df.season) == {"Kharif", "Rabi", "Zaid"}
    # season alone must not identify a crop
    assert (df.groupby("season").crop.nunique() >= 5).all()


# ------------------------------------------------------------------- model
def test_model_probabilities_and_metrics():
    import json
    assert cropy.MODEL is not None
    row = pd.DataFrame([{"humidity": 78, "rainfall": 190, "season": "Kharif", "land_area": 2.0}])
    proba = cropy.MODEL.predict_proba(row)[0]
    assert abs(proba.sum() - 1) < 1e-6
    crop, conf, top = cropy.predict({"humidity": 78, "rainfall": 190, "season": "Kharif", "land_area": 2.0})
    assert crop == cropy.MODEL.classes_[proba.argmax()]
    assert conf == pytest.approx(proba.max() * 100)
    assert len(top) == 3 and top[0]["crop"] == crop
    m = json.load(open(os.path.join(ROOT, "model", "metrics.json")))
    for k in ("accuracy", "precision", "recall", "f1_score"):
        assert 0 < m[k] <= 1
    assert len(m["confusion_matrix"]) == 30


# -------------------------------------------------------------- management
def test_management_matches_dataset_and_schedule_dates():
    df = pd.read_csv(os.path.join(ROOT, "data", "crop_dataset.csv"))
    assert mgmt.validate_management(df.crop.unique())
    start = date(2026, 10, 6)
    for crop, e in mgmt.load_management().items():
        sched = mgmt.build_schedule(crop, start)
        assert sched[0]["task_day"] == 0 and sched[0]["task_date"] == "2026-10-06"
        assert sched[-1]["activity"] == "Harvest"
        assert sched[-1]["task_date"] == (start + timedelta(days=e["duration_days"])).isoformat()
        assert [t["task_day"] for t in sched] == sorted(t["task_day"] for t in sched)
    r = mgmt.build_schedule("Rice", start)
    assert {t["task_day"]: t["task_date"] for t in r}[30] == "2026-11-05"
    # crops have distinct lifecycles
    assert len({tuple(s["day"] for s in e["growth_stages"]) for e in mgmt.load_management().values()}) > 20


def test_task_status():
    t = date(2026, 10, 6)
    assert mgmt.task_status("2026-10-05", False, t) == "Overdue"
    assert mgmt.task_status("2026-10-06", False, t) == "Due Today"
    assert mgmt.task_status("2026-10-07", False, t) == "Upcoming"
    assert mgmt.task_status("2026-10-01", True, t) == "Completed"


# ------------------------------------------------------------ app / SQLite
def test_pages_load(client):
    for path in ["/", "/recommend", "/plan", "/schedule", "/history", "/about", "/crop/Rice"]:
        r = client.get(path)
        assert r.status_code == 200, path
    assert client.get("/crop/Nope").status_code == 404
    assert client.get("/result/9999").status_code == 404


def test_validation_errors(client):
    r = client.post("/recommend", data={"humidity": "abc", "rainfall": "-5", "season": "Winter", "land_area": "0"})
    assert r.status_code == 400
    body = r.get_data(as_text=True)
    assert "valid humidity" in body and "valid rainfall" in body and "Kharif, Rabi or Zaid" in body
    assert "Traceback" not in body


def test_full_flow_and_persistence(client):
    r = client.post("/recommend", data={"humidity": "78", "rainfall": "190", "season": "Kharif", "land_area": "2"})
    assert r.status_code == 302
    pid = int(r.headers["Location"].rsplit("/", 1)[1])
    page = client.get(f"/result/{pid}").get_data(as_text=True)
    assert "Model Confidence" in page and "Why this result?" in page
    row = cropy.db.get_prediction(pid)
    assert f"{row['confidence']:.1f}%" in page

    bad = client.post(f"/result/{pid}/plan", data={"sowing_date": "not-a-date"})
    assert bad.status_code == 400
    sow = date.today() - timedelta(days=20)
    r = client.post(f"/result/{pid}/plan", data={"sowing_date": sow.isoformat()})
    assert r.status_code == 302
    plan_id = int(r.headers["Location"].rsplit("/", 1)[1])
    # posting again does not create a duplicate plan
    r2 = client.post(f"/result/{pid}/plan", data={"start_today": "1"})
    assert r2.headers["Location"].endswith(f"/plan/{plan_id}")
    assert cropy.db.get_prediction(pid)["sowing_date"] == sow.isoformat()

    tasks = cropy.enrich_tasks(cropy.db.plan_tasks(plan_id))
    assert tasks and any(t["status"] == "Overdue" for t in tasks)
    overdue = next(t for t in tasks if t["status"] == "Overdue")
    j = client.post(f"/api/tasks/{overdue['id']}/toggle", json={"completed": True}).get_json()
    assert j["ok"] and j["task"]["status"] == "Completed"
    # persisted: reload from DB
    again = cropy.enrich_tasks(cropy.db.plan_tasks(plan_id))
    assert next(t for t in again if t["id"] == overdue["id"])["status"] == "Completed"
    assert "Completed" in client.get("/schedule").get_data(as_text=True)
    j = client.post(f"/api/tasks/{overdue['id']}/toggle", json={"completed": False}).get_json()
    assert j["task"]["status"] == "Overdue"
    assert client.post("/api/tasks/99999/toggle", json={}).status_code == 404

    hist = client.get("/history").get_data(as_text=True)
    assert row["predicted_crop"] in hist and f"/result/{pid}" in hist
    assert client.get(f"/plan/{plan_id}").status_code == 200
    assert client.get("/").status_code == 200


def test_sql_injection_safe(client):
    r = client.post("/recommend", data={"humidity": "50", "rainfall": "50", "season": "Rabi'; DROP TABLE farm_tasks;--", "land_area": "1"})
    assert r.status_code == 400
    assert cropy.db.list_plans() is not None


# ----------------------------------------------------------------- weather
def _fake_google(calls):
    class R:
        def __init__(self, status, payload):
            self.status_code, self._p = status, payload
        def json(self):
            return self._p

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        assert params["key"] == SECRET
        if url.endswith("currentConditions:lookup"):
            return R(200, {"currentTime": "2026-10-06T14:00:00Z", "timeZone": {"id": "Asia/Kolkata"}, "isDaytime": True,
                           "weatherCondition": {"iconBaseUri": "https://maps.gstatic.com/weather/v1/partly_cloudy", "description": {"text": "Partly cloudy"}, "type": "PARTLY_CLOUDY"},
                           "temperature": {"degrees": 28.4, "unit": "CELSIUS"}, "feelsLikeTemperature": {"degrees": 30.1},
                           "relativeHumidity": 64, "uvIndex": 6, "cloudCover": 40,
                           "precipitation": {"probability": {"percent": 20, "type": "RAIN"}, "qpf": {"quantity": 0.0, "unit": "MILLIMETERS"}},
                           "wind": {"direction": {"cardinal": "NW"}, "speed": {"value": 12, "unit": "KILOMETERS_PER_HOUR"}, "gust": {"value": 20}}})
        if url.endswith("forecast/hours:lookup"):
            return R(200, {"forecastHours": [{"interval": {"startTime": f"2026-10-06T{h:02d}:00:00Z"}, "temperature": {"degrees": 27 + h % 3},
                                              "precipitation": {"probability": {"percent": 70}}, "weatherCondition": {"description": {"text": "Rain"}}} for h in range(30)]})
        if url.endswith("forecast/days:lookup"):
            return R(200, {"forecastDays": [{"displayDate": {"year": 2026, "month": 10, "day": 6 + i}, "maxTemperature": {"degrees": 41 if i == 1 else 30},
                                             "minTemperature": {"degrees": 22},
                                             "daytimeForecast": {"weatherCondition": {"description": {"text": "Sunny"}}, "precipitation": {"probability": {"percent": 10 * i}, "qpf": {"quantity": 2}},
                                                                 "wind": {"speed": {"value": 45 if i == 2 else 10}}},
                                             "nighttimeForecast": {"precipitation": {"probability": {"percent": 5}}}} for i in range(8)]})
        if url.endswith("publicAlerts:lookup"):
            return R(200, {"weatherAlerts": [{"alertTitle": {"text": "Heavy rainfall warning"}, "eventType": "FLOOD", "severity": "SEVERE",
                                              "startTime": "2026-10-07T00:00:00Z", "expirationTime": "2026-10-08T00:00:00Z", "areaName": "Delhi",
                                              "instruction": ["Avoid low-lying areas"], "dataSource": {"name": "IMD", "authorityUri": "https://mausam.imd.gov.in"}}]})
        raise AssertionError(url)
    return fake_get


@pytest.fixture
def clean_weather(monkeypatch):
    wx._cache.clear(); wx._last_forced.clear()
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", SECRET)
    yield
    wx._cache.clear(); wx._last_forced.clear()


def test_weather_normalization_cache_and_advisories(monkeypatch, clean_weather):
    calls = []
    monkeypatch.setattr(wx.requests, "get", _fake_google(calls))
    w = wx.get_weather(28.61, 77.21)
    assert w["available"] and w["current"]["temperature"] == 28.4 and w["current"]["humidity"] == 64
    assert w["current"]["rain_probability"] == 20 and w["current"]["wind_kmh"] == 12
    assert w["current"]["icon"].endswith("partly_cloudy.svg")
    assert len(w["hourly"]) == 24 and len(w["daily"]) == 7
    assert w["daily"][0]["date"] == "2026-10-06" and w["daily"][0]["rain_probability"] == 5
    assert w["alerts"][0]["title"] == "Heavy rainfall warning" and w["alerts"][0]["source"] == "IMD"
    n = len(calls); assert n == 4
    wx.get_weather(28.61, 77.21)           # served from cache
    assert len(calls) == n
    wx.get_weather(28.61, 77.21, refresh=True)   # forced refresh hits API once
    assert len(calls) == 2 * n
    wx.get_weather(28.61, 77.21, refresh=True)   # throttled: cache served
    assert len(calls) == 2 * n

    tasks = [{"activity": "Irrigation Check", "category": "Irrigation", "status": "Due Today", "days_until": 0}]
    adv = wx.weather_advisories(w, tasks)
    titles = " | ".join(a["title"] for a in adv)
    assert "Rain likely, irrigation task pending" in titles
    assert "Extreme heat" in titles and "Strong wind" in titles
    assert all(a["source"] == "CROPY Weather Advisory" for a in adv)
    assert all("must" not in a["message"].lower() for a in adv)


def test_weather_failures_never_crash(monkeypatch, clean_weather):
    class R:
        status_code = 429
        def json(self): return {}
    monkeypatch.setattr(wx.requests, "get", lambda *a, **k: R())
    w = wx.get_weather(10, 10)
    assert not w["available"] and "quota" in w["error"].lower()

    def boom(*a, **k): raise wx.requests.ConnectionError(f"https://x?key={SECRET}")
    monkeypatch.setattr(wx.requests, "get", boom)
    wx._cache.clear()
    w = wx.get_weather(11, 11)
    assert not w["available"] and SECRET not in str(w)

    monkeypatch.delenv("GOOGLE_MAPS_API_KEY")
    w = wx.get_weather(12, 12)
    assert not w["available"] and "not configured" in w["error"]


def test_stale_cache_served_on_failure(monkeypatch, clean_weather):
    calls = []
    monkeypatch.setattr(wx.requests, "get", _fake_google(calls))
    wx.get_weather(20, 20)
    for v in wx._cache.values(): v["at"] -= 10_000   # expire everything
    def boom(*a, **k): raise wx.requests.Timeout()
    monkeypatch.setattr(wx.requests, "get", boom)
    w = wx.get_weather(20, 20)
    assert w["available"] and w["stale"] and w["current"]["temperature"] == 28.4


def test_api_endpoint_and_key_not_leaked(client, monkeypatch, clean_weather):
    monkeypatch.setattr(wx.requests, "get", _fake_google([]))
    j = client.get("/api/weather?lat=28.6&lon=77.2").get_json()
    assert j["available"] and j["alerts"][0]["level"] == "high" and isinstance(j["advisories"], list)
    assert SECRET not in client.get("/api/weather?lat=28.6&lon=77.2").get_data(as_text=True)
    assert client.get("/api/weather?lat=abc&lon=1").status_code == 400
    for path in ["/", "/recommend", "/plan", "/static/js/weather.js", "/static/js/app.js"]:
        assert SECRET not in client.get(path).get_data(as_text=True)


def test_app_works_without_weather(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    j = client.get("/api/weather?lat=28.6&lon=77.2").get_json()
    assert j["available"] is False and j["error"]
    assert client.get("/").status_code == 200
    r = client.post("/recommend", data={"humidity": "60", "rainfall": "70", "season": "Rabi", "land_area": "3"})
    assert r.status_code == 302
