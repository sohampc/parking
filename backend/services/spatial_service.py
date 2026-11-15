"""Spatial, historical and satellite intelligence fusion.

All displayed measurements originate from live external data services. No
placeholder/null/fabricated sensor values are inserted into the final packet.
"""

import math
import os
import sys
from typing import Any, Dict, Optional

services_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(services_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.osm_service import get_osm_service
from services.sentinel_service import get_sentinel_service
from ml.inference import get_inference_engine


class SpatialIntelligenceService:
    def __init__(self):
        self.osm_service = get_osm_service()
        self.sentinel_service = get_sentinel_service()
        self.ai_engine = get_inference_engine()

    @staticmethod
    def _require(value: Any, field: str) -> Any:
        if value is None or value == "":
            raise ValueError(f"Required real observation '{field}' is missing.")
        return value

    def process_hotspot(self, raw_hotspot: Dict[str, Any]) -> Dict[str, Any]:
        lat = float(self._require(raw_hotspot.get("lat"), "lat"))
        lon = float(self._require(raw_hotspot.get("lon"), "lon"))
        brightness = float(self._require(raw_hotspot.get("brightness"), "brightness"))
        frp = float(self._require(raw_hotspot.get("frp"), "frp"))
        conf_firms = float(self._require(raw_hotspot.get("firms_confidence"), "firms_confidence"))
        daynight = str(self._require(raw_hotspot.get("daynight"), "daynight"))
        is_night = 1 if daynight.upper() == "NIGHT" else 0

        osm_context = self.osm_service.query_infrastructure_context(lat, lon)
        dist_ind = float(osm_context["dist_to_industrial_m"])
        dist_res = float(osm_context["dist_to_residential_m"])
        dist_for = float(osm_context["dist_to_forest_m"])
        dist_agr = float(osm_context["dist_to_agriculture_m"])

        sentinel_evidence = self.sentinel_service.get_multi_sensor_evidence(
            lat,
            lon,
            is_industrial_nearby=(dist_ind < 500),
            acq_date=raw_hotspot.get("acq_date"),
        )

        # cluster_size is a real FIRMS-derived field when available. If FIRMS
        # does not provide it, derive it from the live feed in main.py before
        # this service is called. Never insert a made-up default here.
        cluster_size = raw_hotspot.get("cluster_size")
        if cluster_size is None:
            raise ValueError("FIRMS cluster_size is missing; refusing to invent it.")

        p30 = int(self._require(raw_hotspot.get("persistence_count_30d"), "persistence_count_30d"))
        p365 = int(self._require(raw_hotspot.get("persistence_count_365d"), "persistence_count_365d"))

        feature_vector = {
            "brightness": brightness,
            "frp": frp,
            "firms_confidence": conf_firms,
            "dist_to_industrial_m": dist_ind,
            "dist_to_residential_m": dist_res,
            "dist_to_forest_m": dist_for,
            "dist_to_agriculture_m": dist_agr,
            "persistence_count_30d": p30,
            "persistence_count_365d": p365,
            "is_night": is_night,
            "cluster_size": float(cluster_size),
        }

        ai_verdict = self.ai_engine.predict(feature_vector)
        recurrence_text = (
            f"HIGHLY PERSISTENT (Recorded {p30} of past 30 days)"
            if p30 >= 10
            else f"NEW ANOMALY (Recorded {p30} times in past 30 days; {p365} in past year)"
        )

        return {
            "id": self._require(raw_hotspot.get("id"), "id"),
            "lat": lat,
            "lon": lon,
            "region": raw_hotspot.get("region", f"Sector ({lat:.3f}° N, {lon:.3f}° E)"),
            "facility_name": osm_context["nearest_facility_name"],
            "dist_industrial_m": round(dist_ind, 1),
            "dist_residential_m": round(dist_res, 1),
            "nearest_water_source": osm_context["nearest_water_source"],
            "water_distance_m": osm_context["water_distance_m"],
            "dist_forest_m": osm_context["dist_to_forest_m"],
            "dist_agriculture_m": osm_context["dist_to_agriculture_m"],
            "sensor": raw_hotspot.get("satellite", raw_hotspot.get("sensor", "VIIRS")),
            "acq_date": raw_hotspot.get("acq_date", ""),
            "acq_time": self._require(raw_hotspot.get("acq_time"), "acq_time"),
            "brightness_k": brightness,
            "frp_mw": frp,
            "confidence_firms": conf_firms,
            "daynight": daynight,
            "persistence_30d": p30,
            "persistence_365d": p365,
            "recurrence_evaluation": recurrence_text,
            "classification": ai_verdict["predicted_class"],
            "confidence_percent": ai_verdict["confidence_percent"],
            "confidence_rating": ai_verdict["confidence_rating"],
            "threat_level": ai_verdict["threat_assessment"]["threat_level"],
            "threat_score": ai_verdict["threat_assessment"]["threat_score"],
            "emergency_flag": ai_verdict["threat_assessment"]["emergency_flag"],
            "probabilities": ai_verdict["probabilities_percent"],
            "action_text": ai_verdict["threat_assessment"]["recommended_action"],
            "autonomous_reasoning": ai_verdict["autonomous_reasoning"],
            "satellite_evidence": sentinel_evidence,
            "osm_metadata": osm_context,
            "data_provenance": {
                "thermal": "NASA FIRMS live API",
                "osm": "OpenStreetMap Overpass live query",
                "sentinel1": "Copernicus Sentinel-1 via Microsoft Planetary Computer",
                "sentinel2": "Copernicus Sentinel-2 via Microsoft Planetary Computer",
                "classifier": "Random Forest trained on project scenario dataset; see /api/metrics",
            },
        }


_spatial_service: Optional[SpatialIntelligenceService] = None


def get_spatial_intelligence_service() -> SpatialIntelligenceService:
    global _spatial_service
    if _spatial_service is None:
        _spatial_service = SpatialIntelligenceService()
    return _spatial_service
