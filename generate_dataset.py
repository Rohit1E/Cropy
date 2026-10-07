"""CROPY original dataset generator.

Builds data/crop_dataset.csv from hand-defined crop profiles with controlled
variation. No external dataset is used. Output is reproducible (fixed seed).

Rainfall is the typical seasonal/monthly-equivalent rainfall in mm that the crop
is grown under; humidity is mean relative humidity in %; land_area is the plot
size in acres. This is a demonstration dataset, not agronomic ground truth.
"""
import os
import sys

import numpy as np
import pandas as pd

SEED = 42
RECORDS_PER_CROP = 25
MIN_PER_CROP = 20
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "crop_dataset.csv")

# humidity %, rainfall mm, land area acres, seasons (first is primary, ~80% of rows)
# Ranges deliberately overlap between crops and seasons so that no single feature
# (especially season) identifies a crop.
CROP_PROFILES = {
    # ---------------- KHARIF ----------------
    "Rice":         {"humidity_range": (68, 92), "rainfall_range": (140, 300), "area_range": (0.5, 8.0),  "seasons": ["Kharif"]},
    "Maize":        {"humidity_range": (55, 80), "rainfall_range": (80, 200),  "area_range": (1.0, 10.0), "seasons": ["Kharif", "Rabi"]},
    "Cotton":       {"humidity_range": (50, 78), "rainfall_range": (60, 160),  "area_range": (2.0, 15.0), "seasons": ["Kharif"]},
    "Soybean":      {"humidity_range": (60, 85), "rainfall_range": (100, 220), "area_range": (1.5, 12.0), "seasons": ["Kharif"]},
    "Groundnut":    {"humidity_range": (50, 75), "rainfall_range": (70, 170),  "area_range": (1.0, 8.0),  "seasons": ["Kharif"]},
    "Bajra":        {"humidity_range": (35, 62), "rainfall_range": (35, 100),  "area_range": (2.0, 12.0), "seasons": ["Kharif"]},
    "Jowar":        {"humidity_range": (40, 68), "rainfall_range": (45, 120),  "area_range": (2.0, 12.0), "seasons": ["Kharif", "Rabi"]},
    "Pigeon Pea":   {"humidity_range": (52, 78), "rainfall_range": (75, 180),  "area_range": (1.0, 9.0),  "seasons": ["Kharif"]},
    "Moong":        {"humidity_range": (45, 72), "rainfall_range": (50, 130),  "area_range": (0.5, 6.0),  "seasons": ["Kharif"]},
    "Sesame":       {"humidity_range": (42, 70), "rainfall_range": (40, 110),  "area_range": (0.5, 5.0),  "seasons": ["Kharif", "Zaid"]},
    # ---------------- RABI ----------------
    "Wheat":        {"humidity_range": (45, 72), "rainfall_range": (45, 105),  "area_range": (1.0, 15.0), "seasons": ["Rabi"]},
    "Barley":       {"humidity_range": (38, 65), "rainfall_range": (35, 90),   "area_range": (1.0, 9.0),  "seasons": ["Rabi"]},
    "Mustard":      {"humidity_range": (40, 68), "rainfall_range": (30, 85),   "area_range": (0.5, 8.0),  "seasons": ["Rabi"]},
    "Chickpea":     {"humidity_range": (35, 62), "rainfall_range": (30, 80),   "area_range": (1.0, 10.0), "seasons": ["Rabi"]},
    "Lentil":       {"humidity_range": (42, 70), "rainfall_range": (35, 90),   "area_range": (0.5, 6.0),  "seasons": ["Rabi"]},
    "Peas":         {"humidity_range": (55, 80), "rainfall_range": (55, 110),  "area_range": (0.5, 5.0),  "seasons": ["Rabi"]},
    "Potato":       {"humidity_range": (58, 82), "rainfall_range": (50, 115),  "area_range": (0.5, 6.0),  "seasons": ["Rabi"]},
    "Oats":         {"humidity_range": (50, 76), "rainfall_range": (50, 100),  "area_range": (1.0, 8.0),  "seasons": ["Rabi"]},
    "Linseed":      {"humidity_range": (45, 72), "rainfall_range": (40, 95),   "area_range": (0.5, 6.0),  "seasons": ["Rabi"]},
    "Safflower":    {"humidity_range": (32, 58), "rainfall_range": (25, 75),   "area_range": (1.0, 9.0),  "seasons": ["Rabi"]},
    # ---------------- ZAID ----------------
    "Watermelon":       {"humidity_range": (40, 68), "rainfall_range": (20, 70),  "area_range": (0.5, 6.0), "seasons": ["Zaid"]},
    "Muskmelon":        {"humidity_range": (35, 62), "rainfall_range": (15, 60),  "area_range": (0.5, 5.0), "seasons": ["Zaid"]},
    "Cucumber":         {"humidity_range": (55, 82), "rainfall_range": (30, 90),  "area_range": (0.5, 4.0), "seasons": ["Zaid", "Kharif"]},
    "Bitter Gourd":     {"humidity_range": (60, 85), "rainfall_range": (45, 110), "area_range": (0.5, 3.5), "seasons": ["Zaid", "Kharif"]},
    "Bottle Gourd":     {"humidity_range": (58, 84), "rainfall_range": (40, 105), "area_range": (0.5, 4.0), "seasons": ["Zaid", "Kharif"]},
    "Summer Moong":     {"humidity_range": (38, 65), "rainfall_range": (20, 65),  "area_range": (0.5, 6.0), "seasons": ["Zaid"]},
    "Fodder Maize":     {"humidity_range": (50, 78), "rainfall_range": (35, 100), "area_range": (1.0, 8.0), "seasons": ["Zaid", "Kharif"]},
    "Fodder Sorghum":   {"humidity_range": (35, 64), "rainfall_range": (25, 85),  "area_range": (1.0, 9.0), "seasons": ["Zaid", "Kharif"]},
    "Pumpkin":          {"humidity_range": (52, 80), "rainfall_range": (35, 95),  "area_range": (0.5, 5.0), "seasons": ["Zaid", "Kharif"]},
    "Summer Groundnut": {"humidity_range": (40, 68), "rainfall_range": (25, 75),  "area_range": (1.0, 7.0), "seasons": ["Zaid"]},
}

SEASONS = {"Kharif", "Rabi", "Zaid"}
PRIMARY_SEASON_WEIGHT = 0.8


def _sample_in_range(rng, lo, hi):
    """Normal sample centred in the range, clipped to it (controlled variation)."""
    centre = (lo + hi) / 2.0
    sd = (hi - lo) / 6.0
    return float(np.clip(rng.normal(centre, sd), lo, hi))


def _pick_season(rng, seasons):
    if len(seasons) == 1:
        return seasons[0]
    if rng.random() < PRIMARY_SEASON_WEIGHT:
        return seasons[0]
    return str(rng.choice(seasons[1:]))


def generate(seed=SEED, per_crop=RECORDS_PER_CROP):
    rng = np.random.default_rng(seed)
    rows = []
    for crop, p in CROP_PROFILES.items():
        seen = set()
        attempts = 0
        while len(seen) < per_crop and attempts < per_crop * 200:
            attempts += 1
            h = int(round(_sample_in_range(rng, *p["humidity_range"])))
            r = int(round(_sample_in_range(rng, *p["rainfall_range"])))
            a = round(_sample_in_range(rng, *p["area_range"]) * 2) / 2  # 0.5 acre steps
            a = float(np.clip(a, p["area_range"][0], p["area_range"][1]))
            s = _pick_season(rng, p["seasons"])
            key = (h, r, s, a)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"humidity": h, "rainfall": r, "season": s, "land_area": round(a, 1), "crop": crop})
    df = pd.DataFrame(rows)
    df = df.drop_duplicates().sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return df


def validate(df):
    problems = []
    expected = set(CROP_PROFILES)
    found = set(df["crop"].unique())
    if found != expected:
        problems.append(f"crop mismatch: missing={sorted(expected - found)} extra={sorted(found - expected)}")
    if len(expected) != 30:
        problems.append(f"profile count is {len(expected)}, expected 30")
    counts = df["crop"].value_counts()
    low = counts[counts < MIN_PER_CROP]
    if len(low):
        problems.append(f"crops with < {MIN_PER_CROP} samples: {low.to_dict()}")
    if df.duplicated().any():
        problems.append("duplicate rows present")
    if df.isna().any().any():
        problems.append("missing values present")
    if not df["humidity"].between(0, 100).all():
        problems.append("humidity outside 0-100")
    if not df["rainfall"].between(0, 600).all():
        problems.append("rainfall outside 0-600")
    if not df["land_area"].between(0.1, 50).all():
        problems.append("land_area outside 0.1-50")
    if not set(df["season"].unique()) <= SEASONS:
        problems.append("unknown season value")
    for crop, p in CROP_PROFILES.items():
        sub = df[df["crop"] == crop]
        if not sub["humidity"].between(*p["humidity_range"]).all():
            problems.append(f"{crop}: humidity outside profile range")
        if not sub["rainfall"].between(*p["rainfall_range"]).all():
            problems.append(f"{crop}: rainfall outside profile range")
        if not sub["season"].isin(p["seasons"]).all():
            problems.append(f"{crop}: season outside profile")
    # leakage guard: season alone must not determine the crop
    per_season = df.groupby("season")["crop"].nunique()
    if (per_season < 5).any():
        problems.append(f"too few crops share a season: {per_season.to_dict()}")
    return problems


def main():
    print("CROPY Dataset Generator")
    print("-----------------------\n")
    df = generate()
    print(f"Records generated: {len(df)}")
    print(f"Crop classes: {df['crop'].nunique()}\n")
    problems = validate(df)
    if problems:
        print("Dataset validation: FAILED")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    if not 600 <= len(df) <= 900:
        print(f"Dataset validation: FAILED (record count {len(df)} outside 600-900)")
        sys.exit(1)
    print("Dataset validation: PASSED\n")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print("Crop distribution:")
    for crop, n in df["crop"].value_counts().sort_index().items():
        print(f"{crop:<18}{n}")
    print("\nSeason distribution:")
    for s, n in df["season"].value_counts().items():
        print(f"{s:<18}{n}  ({df[df.season == s]['crop'].nunique()} crops)")
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
