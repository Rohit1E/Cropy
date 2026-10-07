"""Train the CROPY Random Forest pipeline and save it with real evaluation metrics."""
import json
import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline

from utils.management import DATASET_PATH, validate_management
from utils.preprocessing import FEATURES, TARGET, build_preprocessor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "crop_model.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "model", "metrics.json")
RANDOM_STATE = 42
TEST_SIZE = 0.2


def main():
    if not os.path.exists(DATASET_PATH):
        print("Dataset not found. Run: python generate_dataset.py")
        sys.exit(1)
    df = pd.read_csv(DATASET_PATH)
    validate_management(df[TARGET].unique())
    print("Dataset and management data are consistent (CSV crops == management crops).")

    X, y = df[FEATURES], df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )

    pipeline = Pipeline([
        ("preprocess", build_preprocessor()),
        ("model", RandomForestClassifier(n_estimators=300, random_state=RANDOM_STATE, n_jobs=-1)),
    ])
    pipeline.fit(X_train, y_train)

    pred = pipeline.predict(X_test)
    labels = list(pipeline.classes_)
    acc = accuracy_score(y_test, pred)
    prec, rec, f1, _ = precision_recall_fscore_support(y_test, pred, average="weighted", zero_division=0)
    cm = confusion_matrix(y_test, pred, labels=labels)
    proba = pipeline.predict_proba(X_test)
    top3 = float(np.mean([t in np.array(labels)[np.argsort(p)[::-1][:3]] for t, p in zip(y_test, proba)]))
    cv = cross_val_score(
        Pipeline([("preprocess", build_preprocessor()),
                  ("model", RandomForestClassifier(n_estimators=300, random_state=RANDOM_STATE, n_jobs=-1))]),
        X, y, cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE), scoring="accuracy",
    )

    metrics = {
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1_score": float(f1),
        "averaging": "weighted",
        "top3_accuracy": top3,
        "cv_accuracy_mean": float(np.mean(cv)),
        "cv_accuracy_std": float(np.std(cv)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "n_classes": len(labels),
        "labels": labels,
        "confusion_matrix": cm.tolist(),
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "note": "Performance on CROPY's generated demonstration dataset.",
    }
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("\nModel Performance")
    print("-----------------")
    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {prec:.4f} (weighted)")
    print(f"Recall:    {rec:.4f} (weighted)")
    print(f"F1 Score:  {f1:.4f} (weighted)")
    print(f"Top-3 accuracy: {top3:.4f}")
    print(f"5-fold CV accuracy: {np.mean(cv):.4f} +/- {np.std(cv):.4f}")
    print("Performance on CROPY's generated demonstration dataset.")
    print(f"\nSaved model:   {MODEL_PATH}\nSaved metrics: {METRICS_PATH}")


if __name__ == "__main__":
    main()
