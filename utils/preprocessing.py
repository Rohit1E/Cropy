"""Shared feature definitions and the scikit-learn preprocessing transformer.

The same ColumnTransformer is part of the saved pipeline, so training and
prediction always encode the season identically.
"""
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC_FEATURES = ["humidity", "rainfall", "land_area"]
CATEGORICAL_FEATURES = ["season"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "crop"
SEASONS = ["Kharif", "Rabi", "Zaid"]


def build_preprocessor():
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(categories=[SEASONS], handle_unknown="error"), CATEGORICAL_FEATURES),
        ]
    )


def to_frame(humidity, rainfall, season, land_area):
    """Single-row DataFrame with the exact training column names/order."""
    return pd.DataFrame(
        [{"humidity": humidity, "rainfall": rainfall, "season": season, "land_area": land_area}],
        columns=FEATURES,
    )
