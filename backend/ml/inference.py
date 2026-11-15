"""
Inference Engine for NASA FIRMS AI Fire & Persistent Thermal Source Classifier
Loads the trained model bundle and performs autonomous end-to-end evaluation:
1. Multi-class prediction
2. Confidence score in percentage (%)
3. Complete class probability distribution in percentage (%)
4. Threat Level (CRITICAL, HIGH, MODERATE, LOW) and Threat Score (0-100)
5. Autonomous Emergency Action Recommendation
"""

import os
import joblib
import numpy as np

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fire_classifier.joblib"
)

class FireInferenceEngine:
    def __init__(self, model_path=None):
        self.model_path = model_path or DEFAULT_MODEL_PATH
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"Model file not found at {self.model_path}. Please run train_model.py first."
            )
        self.bundle = joblib.load(self.model_path)
        self.model = self.bundle["model"]
        self.features = self.bundle["features"]
        self.class_mapping = self.bundle["class_mapping"]
        self.class_display_names = self.bundle["class_display_names"]

    def predict(self, telemetry: dict) -> dict:
        """
        Takes raw telemetry dict, extracts feature vector, runs ML model,
        and returns complete autonomous classification with confidence percentages.
        """
        # Build feature vector in exact training order
        row = []
        missing = [feat for feat in self.features if telemetry.get(feat) is None]
        if missing:
            raise ValueError(f"Missing required real feature(s): {', '.join(missing)}")
        for feat in self.features:
            row.append(float(telemetry[feat]))

        import pandas as pd
        X = pd.DataFrame([row], columns=self.features)
        probas = self.model.predict_proba(X)[0]
        pred_idx = int(np.argmax(probas))
        confidence_pct = round(float(probas[pred_idx]) * 100, 2)

        pred_class_code = self.class_mapping[pred_idx]
        pred_display_name = self.class_display_names[pred_idx]

        # Probability distribution across all classes in percent
        prob_breakdown = {}
        for idx, prob in enumerate(probas):
            display = self.class_display_names[idx]
            prob_breakdown[display] = round(float(prob) * 100, 2)

        # Autonomous Threat & Risk Assessment
        threat_level, threat_score, emergency_flag, action_text = self._assess_threat(
            pred_class_code, confidence_pct, telemetry
        )

        # Autonomous AI Reasoning
        reasoning = self._generate_reasoning(
            pred_class_code, confidence_pct, telemetry, prob_breakdown
        )

        return {
            "predicted_class": pred_class_code,
            "display_name": pred_display_name,
            "confidence_percent": confidence_pct,
            "confidence_rating": "HIGH_CERTAINTY" if confidence_pct >= 85 else ("MODERATE" if confidence_pct >= 65 else "UNCERTAIN"),
            "probabilities_percent": prob_breakdown,
            "threat_assessment": {
                "threat_level": threat_level,
                "threat_score": threat_score,
                "emergency_flag": emergency_flag,
                "recommended_action": action_text,
            },
            "autonomous_reasoning": reasoning,
            "input_features": {k: telemetry.get(k) for k in self.features},
        }

    def _assess_threat(self, class_code: str, confidence_pct: float, telemetry: dict):
        """
        Calculates deterministic Threat Level (CRITICAL, HIGH, MODERATE, LOW)
        and numerical score (0 - 100).
        """
        required = ["frp", "dist_to_industrial_m", "dist_to_residential_m", "persistence_count_30d"]
        missing = [key for key in required if telemetry.get(key) is None]
        if missing:
            raise ValueError(f"Missing real feature(s) for threat assessment: {', '.join(missing)}")
        frp = float(telemetry["frp"])
        dist_ind = float(telemetry["dist_to_industrial_m"])
        dist_res = float(telemetry["dist_to_residential_m"])
        persistence_30d = int(telemetry["persistence_count_30d"])

        threat_score = 0
        threat_level = "LOW"
        emergency_flag = False
        action = "ROUTINE MONITORING — No emergency dispatch required."

        if class_code == "INDUSTRIAL_FIRE_HAZARD":
            # High threat: unexpected fire inside industrial zone
            base = 80
            frp_bonus = min(15, frp * 0.2)
            dist_penalty = max(0, (500 - dist_ind) / 50)
            threat_score = int(min(99, base + frp_bonus + dist_penalty))
            threat_level = "CRITICAL"
            emergency_flag = True
            action = "EMERGENCY: Immediate fire brigade & hazmat dispatch recommended. Initiate geofenced evacuation warning."

        elif class_code == "URBAN_RESIDENTIAL_FIRE":
            base = 70
            dist_res_bonus = max(0, (300 - dist_res) / 30)
            threat_score = int(min(95, base + dist_res_bonus))
            threat_level = "HIGH"
            emergency_flag = True
            action = "HIGH THREAT: Alert city fire rescue. Structure fire detected in dense residential area."

        elif class_code == "FOREST_WILDFIRE":
            threat_score = int(min(85, 60 + min(25, frp * 0.3)))
            threat_level = "HIGH"
            emergency_flag = False
            action = "FOREST ALERT: Notify State Forest Department and NDMA wildfire response unit."

        elif class_code == "AGRICULTURAL_BURNING":
            threat_score = int(min(55, 30 + min(20, frp * 0.2)))
            threat_level = "MODERATE"
            emergency_flag = False
            action = "AIR QUALITY ADVISORY: Notify State Pollution Control Board for crop residue monitoring."

        elif class_code == "PERSISTENT_INDUSTRIAL_FLARE":
            # Low threat: routine flare stack burning regularly
            threat_score = int(max(10, 25 - min(15, persistence_30d * 0.5)))
            threat_level = "LOW"
            emergency_flag = False
            action = "NORMAL OPERATIONS: Verified persistent operational thermal source. Routine log."

        return threat_level, threat_score, emergency_flag, action

    def _generate_reasoning(self, class_code, confidence, telemetry, breakdown):
        points = []
        required = ["dist_to_industrial_m", "dist_to_residential_m", "persistence_count_30d", "frp"]
        missing = [key for key in required if telemetry.get(key) is None]
        if missing:
            raise ValueError(f"Missing real feature(s) for reasoning: {', '.join(missing)}")
        dist_ind = float(telemetry["dist_to_industrial_m"])
        dist_res = float(telemetry["dist_to_residential_m"])
        p30 = int(telemetry["persistence_count_30d"])
        frp = float(telemetry["frp"])

        if dist_ind < 500:
            points.append(f"Proximity to industrial infrastructure: {dist_ind:.0f}m away (OSM verified).")
        if dist_res < 500:
            points.append(f"Proximity to residential buildings: {dist_res:.0f}m away.")

        if p30 > 10:
            points.append(f"High historical recurrence: observed {p30} times in last 30 days (consistent with routine flare).")
        elif p30 == 0:
            points.append("Zero previous detections in last 30 days: indicates sudden/unprecedented thermal event.")

        points.append(f"Fire Radiative Power (FRP): {frp:.1f} MW indicates {'severe' if frp > 35 else 'moderate'} combustion energy.")
        points.append(f"Model assigned {confidence:.1f}% confidence to '{self.class_display_names[list(self.class_mapping.values()).index(class_code)]}'.")
        return points

# Singleton instance helper
_engine = None

def get_inference_engine(model_path=None):
    global _engine
    if _engine is None:
        _engine = FireInferenceEngine(model_path)
    return _engine

if __name__ == "__main__":
    engine = get_inference_engine()

    # Test Case 1: Sudden fire in refinery (Accidental Fire)
    test_accident = {
        "brightness": 372.5,
        "frp": 58.4,
        "firms_confidence": 95.0,
        "dist_to_industrial_m": 120.0,
        "dist_to_residential_m": 1200.0,
        "dist_to_forest_m": 8000.0,
        "dist_to_agriculture_m": 5000.0,
        "persistence_count_30d": 0,
        "persistence_count_365d": 0,
        "is_night": 1,
        "cluster_size": 3,
    }

    # Test Case 2: Routine refinery flare (Persistent Flare)
    test_flare = {
        "brightness": 352.0,
        "frp": 22.0,
        "firms_confidence": 90.0,
        "dist_to_industrial_m": 60.0,
        "dist_to_residential_m": 2500.0,
        "dist_to_forest_m": 12000.0,
        "dist_to_agriculture_m": 6000.0,
        "persistence_count_30d": 24,
        "persistence_count_365d": 210,
        "is_night": 1,
        "cluster_size": 1,
    }

    print("\n--- TEST CASE 1: SUDDEN UNPRECEDENTED REFINERY HEAT ---")
    res1 = engine.predict(test_accident)
    print(f"Class:      {res1['display_name']}")
    print(f"Confidence: {res1['confidence_percent']}%")
    print(f"Threat:     {res1['threat_assessment']['threat_level']} (Score: {res1['threat_assessment']['threat_score']})")
    print(f"Emergency:  {res1['threat_assessment']['emergency_flag']}")
    print("Probabilities Breakdown (%):")
    for k, v in res1['probabilities_percent'].items():
        print(f"  • {k:30s}: {v}%")

    print("\n--- TEST CASE 2: KNOWN PERSISTENT REFINERY FLARE ---")
    res2 = engine.predict(test_flare)
    print(f"Class:      {res2['display_name']}")
    print(f"Confidence: {res2['confidence_percent']}%")
    print(f"Threat:     {res2['threat_assessment']['threat_level']} (Score: {res2['threat_assessment']['threat_score']})")
    print(f"Emergency:  {res2['threat_assessment']['emergency_flag']}")
    print("Probabilities Breakdown (%):")
    for k, v in res2['probabilities_percent'].items():
        print(f"  • {k:30s}: {v}%")
