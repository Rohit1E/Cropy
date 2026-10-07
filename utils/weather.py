"""Google Maps Platform Weather API service for CROPY.

- All calls are made server-side; the API key never reaches the browser.
- Responses are normalized into {"current", "hourly", "daily", "alerts"}.
- Short in-memory caching avoids needless requests (and billing); a stale copy is
  served if a refresh fails. Manual refresh is throttled.
- Any failure degrades to "Weather unavailable"; it never raises into the app.
- Rule-based "CROPY Weather Advisory" messages are generated here, transparently.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests

BASE_URL = "https://weather.googleapis.com/v1"
TIMEOUT = (4, 8)  # connect, read seconds

TTL = {"current": 10 * 60, "hourly": 15 * 60, "daily": 60 * 60, "alerts": 10 * 60}
MIN_REFRESH_INTERVAL = 30  # seconds between forced refreshes of the same location

HOURLY_COUNT = 24
DAILY_COUNT = 7

# advisory thresholds (transparent, editable)
RAIN_PROB_THRESHOLD = 60       # percent
HEAVY_RAIN_MM = 50             # mm/day
HEAT_WARNING_C = 36
HEAT_HIGH_C = 40
WIND_WARNING_KMH = 40
GUST_WARNING_KMH = 55
COLD_INFO_C = 5

_cache = {}
_last_forced = {}
_lock = threading.Lock()


# ------------------------------------------------------------------ Open-Meteo fallback
# Used for local/demo installs when GOOGLE_MAPS_API_KEY is not configured.
# It is live weather data, not generated/random data.
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain",
    67: "Heavy freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Rain showers", 81: "Rain showers", 82: "Heavy rain showers",
    85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}

def _wmo(code):
    return _WMO.get(code, "Unknown")


def _open_meteo_request(lat, lon):
    params = {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "forecast_days": DAILY_COUNT,
        "current": ",".join([
            "temperature_2m", "apparent_temperature", "relative_humidity_2m",
            "precipitation", "rain", "weather_code", "cloud_cover",
            "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
            "uv_index", "is_day"
        ]),
        "hourly": ",".join([
            "temperature_2m", "precipitation_probability", "relative_humidity_2m",
            "wind_speed_10m", "weather_code"
        ]),
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_probability_max", "precipitation_sum",
            "wind_speed_10m_max", "wind_gusts_10m_max"
        ]),
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT)
    except requests.Timeout:
        raise WeatherError("The fallback weather service timed out.") from None
    except requests.RequestException:
        raise WeatherError("The fallback weather service could not be reached.") from None
    if resp.status_code >= 400:
        raise WeatherError("The fallback weather service returned an error.")
    try:
        return resp.json()
    except ValueError:
        raise WeatherError("The fallback weather service returned unreadable data.") from None


def _normalize_open_meteo(raw):
    c = raw.get("current") or {}
    cur_code = c.get("weather_code")
    current = {
        "temperature": _num(c.get("temperature_2m")),
        "feels_like": _num(c.get("apparent_temperature")),
        "humidity": c.get("relative_humidity_2m"),
        "rain_probability": None,
        "precipitation_mm": _num(c.get("precipitation")),
        "wind_kmh": _num(c.get("wind_speed_10m")),
        "wind_gust_kmh": _num(c.get("wind_gusts_10m")),
        "wind_direction": None,
        "cloud_cover": c.get("cloud_cover"),
        "uv_index": c.get("uv_index"),
        "condition": _wmo(cur_code),
        "condition_type": cur_code,
        "icon": "emoji:" + ("☀️" if cur_code in (0, 1) else "⛅" if cur_code in (2, 3) else "🌧️" if cur_code and 50 <= cur_code < 90 else "⛈️" if cur_code and cur_code >= 95 else "🌫️"),
        "is_daytime": bool(c.get("is_day", 1)),
        "time": c.get("time"),
        "timezone": raw.get("timezone"),
    }

    h = raw.get("hourly") or {}
    hourly = []
    times = h.get("time") or []
    for i, t in enumerate(times[:HOURLY_COUNT]):
        code = (h.get("weather_code") or [None] * len(times))[i]
        hourly.append({
            "time": t,
            "hour": None,
            "temperature": _num((h.get("temperature_2m") or [None] * len(times))[i]),
            "rain_probability": (h.get("precipitation_probability") or [None] * len(times))[i],
            "humidity": (h.get("relative_humidity_2m") or [None] * len(times))[i],
            "wind_kmh": _num((h.get("wind_speed_10m") or [None] * len(times))[i]),
            "condition": _wmo(code),
            "icon": "emoji:" + ("☀️" if code in (0, 1) else "⛅" if code in (2, 3) else "🌧️" if code and 50 <= code < 90 else "⛈️" if code and code >= 95 else "🌫️"),
        })

    d = raw.get("daily") or {}
    daily = []
    dates = d.get("time") or []
    for i, day in enumerate(dates[:DAILY_COUNT]):
        code = (d.get("weather_code") or [None] * len(dates))[i]
        daily.append({
            "date": day,
            "max_temp": _num((d.get("temperature_2m_max") or [None] * len(dates))[i]),
            "min_temp": _num((d.get("temperature_2m_min") or [None] * len(dates))[i]),
            "rain_probability": (d.get("precipitation_probability_max") or [None] * len(dates))[i],
            "precipitation_mm": _num((d.get("precipitation_sum") or [None] * len(dates))[i]),
            "wind_kmh": _num((d.get("wind_speed_10m_max") or [None] * len(dates))[i]),
            "wind_gust_kmh": _num((d.get("wind_gusts_10m_max") or [None] * len(dates))[i]),
            "humidity": None,
            "condition": _wmo(code),
            "icon": "emoji:" + ("☀️" if code in (0, 1) else "⛅" if code in (2, 3) else "🌧️" if code and 50 <= code < 90 else "⛈️" if code and code >= 95 else "🌫️"),
        })
    return current, hourly, daily


# ------------------------------------------------------------------ helpers
def api_key():
    return (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()


def _key(lat, lon):
    return (round(float(lat), 2), round(float(lon), 2))


def _get(d, *path, default=None):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


class WeatherError(Exception):
    """Carries a user-safe message (never contains the API key)."""


def _request(endpoint, lat, lon, extra=None):
    key = api_key()
    if not key:
        raise WeatherError("Google Weather API key is not configured.")
    params = {"key": key, "location.latitude": lat, "location.longitude": lon}
    if extra:
        params.update(extra)
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=TIMEOUT)
    except requests.Timeout:
        raise WeatherError("The weather service timed out.") from None
    except requests.RequestException:
        raise WeatherError("The weather service could not be reached.") from None
    if resp.status_code == 429:
        raise WeatherError("Weather API quota exceeded.")
    if resp.status_code in (400, 401, 403):
        raise WeatherError("Weather API rejected the request. Check the API key and that the Weather API is enabled.")
    if resp.status_code == 404:
        raise WeatherError("Weather data is not available for this location.")
    if resp.status_code >= 400:
        raise WeatherError("The weather service returned an error.")
    try:
        return resp.json()
    except ValueError:
        raise WeatherError("The weather service returned an unreadable response.") from None


# ------------------------------------------------------------ normalization
def _icon(cond):
    base = _get(cond, "iconBaseUri")
    return f"{base}.svg" if base else None


def _num(v):
    return round(v, 1) if isinstance(v, (int, float)) else None


def normalize_current(raw):
    cond = raw.get("weatherCondition") or {}
    return {
        "temperature": _num(_get(raw, "temperature", "degrees")),
        "feels_like": _num(_get(raw, "feelsLikeTemperature", "degrees")),
        "humidity": _get(raw, "relativeHumidity"),
        "rain_probability": _get(raw, "precipitation", "probability", "percent"),
        "precipitation_mm": _num(_get(raw, "precipitation", "qpf", "quantity")),
        "wind_kmh": _num(_get(raw, "wind", "speed", "value")),
        "wind_gust_kmh": _num(_get(raw, "wind", "gust", "value")),
        "wind_direction": _get(raw, "wind", "direction", "cardinal"),
        "cloud_cover": _get(raw, "cloudCover"),
        "uv_index": _get(raw, "uvIndex"),
        "condition": _get(cond, "description", "text") or "Unknown",
        "condition_type": cond.get("type"),
        "icon": _icon(cond),
        "is_daytime": raw.get("isDaytime"),
        "time": raw.get("currentTime"),
        "timezone": _get(raw, "timeZone", "id"),
    }


def normalize_hourly(raw):
    out = []
    for h in (raw.get("forecastHours") or [])[:HOURLY_COUNT]:
        cond = h.get("weatherCondition") or {}
        out.append({
            "time": _get(h, "interval", "startTime"),
            "hour": _get(h, "displayDateTime", "hours"),
            "temperature": _num(_get(h, "temperature", "degrees")),
            "rain_probability": _get(h, "precipitation", "probability", "percent"),
            "humidity": h.get("relativeHumidity"),
            "wind_kmh": _num(_get(h, "wind", "speed", "value")),
            "condition": _get(cond, "description", "text") or "",
            "icon": _icon(cond),
        })
    return out


def normalize_daily(raw):
    out = []
    for d in (raw.get("forecastDays") or [])[:DAILY_COUNT]:
        day, night = d.get("daytimeForecast") or {}, d.get("nighttimeForecast") or {}
        cond = day.get("weatherCondition") or night.get("weatherCondition") or {}
        probs = [p for p in (_get(day, "precipitation", "probability", "percent"),
                             _get(night, "precipitation", "probability", "percent")) if p is not None]
        qpfs = [q for q in (_get(day, "precipitation", "qpf", "quantity"),
                            _get(night, "precipitation", "qpf", "quantity")) if q is not None]
        dd = d.get("displayDate") or {}
        try:
            iso = date(int(dd["year"]), int(dd["month"]), int(dd["day"])).isoformat()
        except (KeyError, TypeError, ValueError):
            iso = None
        winds = [w for w in (_get(day, "wind", "speed", "value"), _get(night, "wind", "speed", "value")) if w is not None]
        gusts = [w for w in (_get(day, "wind", "gust", "value"), _get(night, "wind", "gust", "value")) if w is not None]
        out.append({
            "date": iso,
            "max_temp": _num(_get(d, "maxTemperature", "degrees")),
            "min_temp": _num(_get(d, "minTemperature", "degrees")),
            "rain_probability": max(probs) if probs else None,
            "precipitation_mm": _num(sum(qpfs)) if qpfs else None,
            "wind_kmh": _num(max(winds)) if winds else None,
            "wind_gust_kmh": _num(max(gusts)) if gusts else None,
            "humidity": day.get("relativeHumidity"),
            "condition": _get(cond, "description", "text") or "",
            "icon": _icon(cond),
        })
    return out


def normalize_alerts(raw):
    out = []
    for a in raw.get("weatherAlerts") or []:
        instr = a.get("instruction") or []
        if isinstance(instr, str):
            instr = [instr]
        out.append({
            "title": _get(a, "alertTitle", "text") or a.get("eventType") or "Weather alert",
            "event_type": a.get("eventType"),
            "severity": a.get("severity"),
            "urgency": a.get("urgency"),
            "start": a.get("startTime"),
            "end": a.get("expirationTime"),
            "area": a.get("areaName"),
            "description": a.get("description"),
            "instructions": [i for i in instr if i],
            "source": _get(a, "dataSource", "name"),
            "source_url": _get(a, "dataSource", "authorityUri"),
        })
    return out


FETCHERS = {
    "current": ("currentConditions:lookup", None, normalize_current),
    "hourly": ("forecast/hours:lookup", {"hours": HOURLY_COUNT, "pageSize": HOURLY_COUNT}, normalize_hourly),
    "daily": ("forecast/days:lookup", {"days": DAILY_COUNT, "pageSize": DAILY_COUNT}, normalize_daily),
    "alerts": ("publicAlerts:lookup", None, normalize_alerts),
}


# ------------------------------------------------------------------ service
def _fetch_part(part, lat, lon, force):
    """Return (data, error, stale). Uses cache unless expired or forced."""
    ck = (part,) + _key(lat, lon)
    now = time.time()
    with _lock:
        hit = _cache.get(ck)
    if hit and not force and now - hit["at"] < TTL[part]:
        return hit["data"], None, False
    endpoint, extra, norm = FETCHERS[part]
    try:
        data = norm(_request(endpoint, lat, lon, extra))
    except WeatherError as e:
        if hit:  # serve the stale copy rather than nothing
            return hit["data"], str(e), True
        return None, str(e), False
    except Exception:  # never let a parsing surprise crash the app
        if hit:
            return hit["data"], "Unexpected weather data format.", True
        return None, "Unexpected weather data format.", False
    with _lock:
        _cache[ck] = {"data": data, "at": now}
    return data, None, False


def get_weather(lat, lon, refresh=False):
    """Normalized weather for a coordinate. Always returns a dict; never raises."""
    result = {
        "available": False, "error": None, "stale": False, "alerts_available": True, "source": "Google Weather",
        "fetched_at": None, "current": None, "hourly": [], "daily": [], "alerts": [],
        "location": {"lat": lat, "lon": lon},
    }
    # Prefer Google Weather when configured. If no key is present, use the
    # real Open-Meteo fallback so local/demo installs still have live weather.
    if not api_key():
        try:
            raw = _open_meteo_request(lat, lon)
            current, hourly, daily = _normalize_open_meteo(raw)
            result.update({
                "available": True, "current": current, "hourly": hourly, "daily": daily,
                "fetched_at": time.time(), "alerts_available": False,
                "source": "Open-Meteo",
            })
            return result
        except WeatherError as e:
            result["error"] = str(e)
            return result

    force = False
    if refresh:
        k = _key(lat, lon)
        now = time.time()
        with _lock:
            if now - _last_forced.get(k, 0) >= MIN_REFRESH_INTERVAL:
                _last_forced[k] = now
                force = True

    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {p: ex.submit(_fetch_part, p, lat, lon, force) for p in FETCHERS}
        parts = {p: f.result() for p, f in futs.items()}

    errors = []
    for part in ("current", "hourly", "daily"):
        data, err, stale = parts[part]
        if data is not None:
            result[part] = data
        if err:
            errors.append(err)
        result["stale"] = result["stale"] or stale
    a_data, a_err, a_stale = parts["alerts"]
    if a_data is not None:
        result["alerts"] = a_data
    if a_err and a_data is None:
        result["alerts_available"] = False
    result["stale"] = result["stale"] or a_stale

    result["available"] = bool(result["current"] or result["daily"] or result["hourly"])
    if not result["available"]:
        result["error"] = errors[0] if errors else "Weather data is temporarily unavailable."
    elif errors:
        result["error"] = errors[0]
    ts = [_cache[(p,) + _key(lat, lon)]["at"] for p in ("current", "daily") if (p,) + _key(lat, lon) in _cache]
    result["fetched_at"] = max(ts) if ts else None
    return result


# ----------------------------------------------------------------- advisory
def weather_advisories(weather, tasks=None):
    """Transparent rule-based advisories ("CROPY Weather Advisory").

    `tasks` is an optional list of dicts with keys: activity, category, status, days_until.
    Official public alerts are shown separately and never rewritten here.
    """
    if not weather or not weather.get("available"):
        return []
    tasks = tasks or []
    out = []
    daily = (weather.get("daily") or [])[:3]
    hourly = weather.get("hourly") or []
    cur = weather.get("current") or {}

    def add(level, title, message):
        out.append({"level": level, "title": title, "message": message, "source": "CROPY Weather Advisory"})

    # --- rain
    probs = [h["rain_probability"] for h in hourly if h.get("rain_probability") is not None]
    probs += [d["rain_probability"] for d in daily[:2] if d.get("rain_probability") is not None]
    if cur.get("rain_probability") is not None:
        probs.append(cur["rain_probability"])
    max_rain = max(probs) if probs else None
    irrigation = [t for t in tasks if t.get("category") == "Irrigation"
                  and t.get("status") in ("Due Today", "Overdue", "Upcoming")
                  and (t.get("status") != "Upcoming" or (t.get("days_until") is not None and t["days_until"] <= 2))]
    heavy = [d for d in daily[:3] if (d.get("precipitation_mm") or 0) >= HEAVY_RAIN_MM]
    if heavy:
        add("warning", "Heavy rain forecast",
            f"Heavy rain is forecast (about {heavy[0]['precipitation_mm']:.0f} mm). Weather condition may affect "
            "field operations and drainage. Consider reviewing scheduled irrigation and fertilizer tasks.")
    elif max_rain is not None and max_rain >= RAIN_PROB_THRESHOLD:
        if irrigation:
            add("warning", "Rain likely, irrigation task pending",
                f"Rain is likely ({max_rain:.0f}% chance). Consider reviewing the scheduled irrigation task "
                f"({irrigation[0]['activity']}) before proceeding.")
        else:
            add("info", "Rain likely",
                f"Rain is likely ({max_rain:.0f}% chance). Weather condition may affect field work and spraying.")

    # --- heat
    temps = [d["max_temp"] for d in daily if d.get("max_temp") is not None]
    if cur.get("temperature") is not None:
        temps.append(cur["temperature"])
    if temps:
        hot = max(temps)
        if hot >= HEAT_HIGH_C:
            add("high", "Extreme heat forecast",
                f"High temperature conditions are forecast (up to {hot:.0f}°C). Monitor crop water requirements closely.")
        elif hot >= HEAT_WARNING_C:
            add("warning", "High heat forecast",
                f"High heat conditions are forecast (up to {hot:.0f}°C). Monitor crop water requirements.")

    # --- wind
    winds = [d["wind_kmh"] for d in daily if d.get("wind_kmh") is not None]
    gusts = [d["wind_gust_kmh"] for d in daily if d.get("wind_gust_kmh") is not None]
    for v in (cur.get("wind_kmh"),):
        if v is not None:
            winds.append(v)
    if cur.get("wind_gust_kmh") is not None:
        gusts.append(cur["wind_gust_kmh"])
    if (winds and max(winds) >= WIND_WARNING_KMH) or (gusts and max(gusts) >= GUST_WARNING_KMH):
        peak = max(winds + gusts) if (winds or gusts) else 0
        add("warning", "Strong wind forecast",
            f"Strong wind conditions are forecast (up to {peak:.0f} km/h). Consider inspecting vulnerable or tall crops.")

    # --- cold
    mins = [d["min_temp"] for d in daily if d.get("min_temp") is not None]
    if mins and min(mins) <= COLD_INFO_C:
        add("info", "Cold nights forecast",
            f"Low night temperatures are forecast (down to {min(mins):.0f}°C). Weather condition may affect frost-sensitive crops.")
    return out


def official_alert_level(alert):
    sev = (alert.get("severity") or "").upper()
    return "high" if sev in ("EXTREME", "SEVERE") else "warning"
