"""
Model Trainer for NASA FIRMS Fire & Persistent Thermal Source Classifier
Trains an ensemble Random Forest classifier on multimodal spatial, thermal, and temporal features.
Outputs validation metrics (Precision, Recall, F1, Confusion Matrix) and serializes the model to joblib.
"""

import os
import json
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

FEATURE_COLUMNS = [
    "brightness",
    "frp",
    "firms_confidence",
    "dist_to_industrial_m",
    "dist_to_residential_m",
    "dist_to_forest_m",
    "dist_to_agriculture_m",
    "persistence_count_30d",
    "persistence_count_365d",
    "is_night",
    "cluster_size",
]

CLASS_MAPPING = {
    0: "INDUSTRIAL_FIRE_HAZARD",
    1: "PERSISTENT_INDUSTRIAL_FLARE",
    2: "URBAN_RESIDENTIAL_FIRE",
    3: "FOREST_WILDFIRE",
    4: "AGRICULTURAL_BURNING",
}

CLASS_DISPLAY_NAMES = {
    0: "Industrial Fire Hazard",
    1: "Persistent Industrial Flare",
    2: "Urban / Residential Fire",
    3: "Forest / Wildfire",
    4: "Agricultural Stubble Burning",
}

def train_fire_classifier(dataset_csv=None, output_model_path=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if dataset_csv is None:
        dataset_csv = os.path.join(script_dir, "training_dataset.csv")
    if output_model_path is None:
        output_model_path = os.path.join(script_dir, "fire_classifier.joblib")

    print(f"Loading training data from {dataset_csv}...")
    df = pd.read_csv(dataset_csv)

    X = df[FEATURE_COLUMNS]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"Training set: {len(X_train)} samples | Test set: {len(X_test)} samples")
    print("Training Random Forest Ensemble with 150 estimators...")

    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=1,
    )
    model.fit(X_train, y_train)

    # Evaluation
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report_dict = classification_report(
        y_test,
        y_pred,
        target_names=[CLASS_MAPPING[i] for i in range(5)],
        output_dict=True,
    )
    report_text = classification_report(
        y_test,
        y_pred,
        target_names=[CLASS_DISPLAY_NAMES[i] for i in range(5)],
        digits=4,
    )
    cm = confusion_matrix(y_test, y_pred).tolist()

    # Feature importances
    feature_importances = dict(
        sorted(
            zip(FEATURE_COLUMNS, [round(float(v), 4) for v in model.feature_importances_]),
            key=lambda x: x[1],
            reverse=True,
        )
    )

    print("\n=======================================================")
    print("               MODEL VALIDATION METRICS                ")
    print("=======================================================")
    print(f"Overall Accuracy: {acc * 100:.2f}%\n")
    print(report_text)
    print("Feature Importances:")
    for feat, imp in feature_importances.items():
        print(f"  • {feat:25s}: {imp * 100:.2f}%")
    print("=======================================================\n")

    # Package model bundle
    bundle = {
        "model": model,
        "features": FEATURE_COLUMNS,
        "class_mapping": CLASS_MAPPING,
        "class_display_names": CLASS_DISPLAY_NAMES,
        "metrics": {
            "validation_dataset_type": "synthetic_scenario_dataset",
            "validation_note": "These metrics validate the model against the project's generated scenario dataset, not against an independently labelled real-world satellite dataset.",
            "accuracy": round(acc, 4),
            "classification_report": report_dict,
            "confusion_matrix": cm,
            "feature_importances": feature_importances,
        },
    }

    joblib.dump(bundle, output_model_path)
    print(f"Model successfully saved to: {output_model_path}")

    # Also save metrics as readable JSON
    metrics_path = os.path.join(script_dir, "validation_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(bundle["metrics"], f, indent=2)
    print(f"Validation metrics exported to: {metrics_path}")

    return bundle

if __name__ == "__main__":
    train_fire_classifier()
