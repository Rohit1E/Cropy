# CROPY

**Crop Recommendation & Management Planning System**: a BCA (Artificial Intelligence & Data Science) academic project.

## Purpose
CROPY moves a user through one workflow: see local weather and time, enter farming conditions, get a Random Forest crop recommendation with real model confidence, read the crop's management plan and lifecycle, start a dated task schedule, and see weather-aware farm alerts. Every prediction, plan and task is stored in SQLite.

## Dataset
An original synthetic/demo dataset generated for this project by `generate_dataset.py` (no Kaggle or other public CSV is used). Each of the 30 crops has a hand-defined profile (humidity range, rainfall range, land-area range, seasons) and the script samples around it with a fixed seed (reproducible). Ranges deliberately overlap so season alone cannot identify a crop (several crops share each season). The script removes duplicates, validates ranges, checks that all 30 crops have enough samples, shuffles, saves `data/crop_dataset.csv` and prints statistics (about 750 records, 25 per crop).

## 30 crops
- **Kharif:** Rice, Maize, Cotton, Soybean, Groundnut, Bajra, Jowar, Pigeon Pea, Moong, Sesame
- **Rabi:** Wheat, Barley, Mustard, Chickpea, Lentil, Peas, Potato, Oats, Linseed, Safflower
- **Zaid:** Watermelon, Muskmelon, Cucumber, Bitter Gourd, Bottle Gourd, Summer Moong, Fodder Maize, Fodder Sorghum, Pumpkin, Summer Groundnut

Some crops are listed in more than one season in the data (for example Maize, Jowar, Sesame, Cucumber) to reflect regional overlap.

## ML
`train_model.py` trains a scikit-learn `Pipeline` (`ColumnTransformer` with `StandardScaler` for numeric features and `OneHotEncoder` for season, then `RandomForestClassifier`). It uses a stratified `train_test_split` with a fixed `random_state`, computes real accuracy, weighted precision/recall/F1, top-3 accuracy, 5-fold CV accuracy and the confusion matrix, and saves the whole pipeline to `model/crop_model.pkl` and metrics to `model/metrics.json`. Confidence shown in the app is `predict_proba` from the saved model. Nothing is hardcoded.

> Metrics describe performance on CROPY's generated demonstration dataset. They are not real agricultural validation. Because crop conditions overlap, single-crop accuracy is moderate while top-3 accuracy is much higher; the result page lists the next closest crops.

## Inputs
Humidity (%), Rainfall (mm), Season (Kharif / Rabi / Zaid), Land Area (acres).

## Management
`data/crop_management.json` is CROPY's own structured database: overview, conditions, fertilizer, NPK, quantities, irrigation, crop-specific growth stages and lifecycle days, dated-able farming tasks, pest monitoring, harvest and duration. Training and app startup verify that the crops in the CSV equal the crops in the JSON.

## Schedule
After a recommendation, choose a sowing date or "Start Schedule Today". CROPY turns the crop's lifecycle days into real calendar dates and stores the plan in SQLite (`farm_plans`, `farm_tasks`). Each task is Upcoming, Due Today, Overdue or Completed, and "Mark Complete" persists across reloads.

## Weather
Google Maps Platform **Weather API** (current conditions, hourly forecast, daily forecast, public alerts), called only from Flask (`utils/weather.py`); the key never reaches the browser. Responses are normalized to `{current, hourly, daily, alerts}`. Caching: current and alerts 10 min, hourly 15 min, daily 60 min, with a **Refresh Weather** button (throttled to once per 30 s per location). If a refresh fails, the last cached data is shown and labelled. If the key is missing, quota is exceeded or the network is down, the UI says "Weather unavailable" and the rest of the app keeps working.

**CROPY Weather Advisory** is a transparent rule set (rain probability, heavy rain, heat, wind, cold, combined with pending irrigation tasks). Thresholds are constants at the top of `utils/weather.py`. Messages are phrased as "Consider reviewing..." and are not produced by the ML model. Official public alerts are shown separately and unedited.

### Google API setup and cost
1. Create a project in Google Cloud Console and enable billing.
2. Enable the **Weather API** (Google Maps Platform).
3. Create an API key under APIs & Services > Credentials and restrict it to the Weather API (and by IP if you can).
4. Copy `.env.example` to `.env` and set `GOOGLE_MAPS_API_KEY=your_key`.

Google Maps Platform uses authenticated access with usage, quota and billing rules, so do not assume unlimited free use. At the time of writing, Google's pricing page lists a free usage cap for the Weather Usage SKU (70,000 for India pricing) with billing beyond it; check the current pricing page. CROPY limits calls by caching, never polling in the background, and throttling manual refresh. Google also offers a Maps Demo Key for Weather API prototyping; use your own key for normal use.

## Time
The header clock uses the browser's local time. The weather response also carries the location's time zone id. The optional Google Time Zone API is not required and is not called.

## Location
"Use My Location" uses browser geolocation after permission. If denied, pick a city or enter latitude/longitude. Only coordinates and a label are stored, in this browser's local storage; the crop recommendation never needs a location.

## Database
SQLite (`database/cropy.db`, created automatically): `prediction_history`, `farm_plans`, `farm_tasks`. All SQL is parameterized.

## Setup
```text
python -m venv venv
venv\Scripts\activate          (Windows)   |   source venv/bin/activate   (macOS/Linux)
pip install -r requirements.txt
python generate_dataset.py
python train_model.py
copy .env.example .env          (then add your key; optional)
python app.py
```
Open http://127.0.0.1:5000. Run tests with `pip install pytest` then `python -m pytest tests -q`.

## Project layout
`app.py` (routes and JSON APIs), `generate_dataset.py`, `train_model.py`, `utils/` (preprocessing, database, management, weather, validation), `templates/`, `static/`, `data/`, `model/`, `database/`, `tests/`.
