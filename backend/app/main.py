"""FastAPI backend for the NTRO Thermal Anomaly & Industrial Fire Intelligence Platform."""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(backend_dir)
load_dotenv(os.path.join(project_root, ".env"), override=False)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.firms_service import get_firms_service, FirmsConfigurationError
from services.osm_service import get_osm_service, OsmDataError, haversine_distance
from services.sentinel_service import get_sentinel_service, SentinelDataError
from services.spatial_service import get_spatial_intelligence_service
from services.weather_service import get_current_wind

app = FastAPI(
    title="NTRO Thermal Intelligence & Fire Classifier API",
    description="Live NASA FIRMS + OSM + Copernicus Sentinel evidence and AI classification.",
    version="2.1.0",
)

# Local/demo deployment only. Restrict this in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

firms_service = get_firms_service()
osm_service = get_osm_service()
sentinel_service = get_sentinel_service()
spatial_service = get_spatial_intelligence_service()


class CustomPointAnalysis(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    # Optional only as a way to search a known FIRMS observation. We do not
    # invent thermal telemetry when these are absent.
    search_radius_km: float = Field(5.0, gt=0, le=25)


class SosRequest(BaseModel):
    facility_code: str
    facility_name: str
    hazard_type: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    reported_by: str = "Plant Safety Control Officer"


@app.get("/api/health")
def health_check():
    return {
        "status": "OPERATIONAL" if firms_service.map_key else "CONFIGURATION_REQUIRED",
        "system": "NTRO Thermal Anomaly & Fire Intelligence Platform",
        "services": {
            "nasa_firms": "CONFIGURED" if firms_service.map_key else "ACTION_REQUIRED: NASA_FIRMS_MAP_KEY",
            "openstreetmap_overpass": "LIVE",
            "copernicus_sentinel_1": "LIVE_CATALOG_AND_ASSET_ACCESS",
            "copernicus_sentinel_2": "LIVE_CATALOG_AND_ASSET_ACCESS",
            "ai_classifier": "LOADED",
        },
        "version": "2.1.0",
    }


@app.get("/api/config/status")
def config_status():
    """Safe configuration diagnostic; never returns the actual MAP_KEY."""
    key = (firms_service.map_key or "").strip()
    return {
        "firms_key_configured": bool(key),
        "firms_key_length": len(key),
        "message": "NASA FIRMS MAP_KEY is loaded from .env." if key else "NASA FIRMS MAP_KEY is not loaded. Put it in the project-root .env file.",
    }


@app.get("/api/metrics")
def get_validation_metrics():
    metrics_file = os.path.join(backend_dir, "ml", "validation_metrics.json")
    if os.path.exists(metrics_file):
        with open(metrics_file, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Metrics file not found")


def _attach_live_history(item: Dict[str, Any]) -> Dict[str, Any]:
    """Attach actual historical FIRMS counts. No hard-coded counts."""
    lat, lon = float(item["lat"]), float(item["lon"])
    # Small spatial window around each detection. The counts are derived from
    # actual FIRMS records returned by NASA, not from the hotspot identity.
    item["persistence_count_30d"] = firms_service.fetch_historical_count(lat, lon, 30, radius_deg=0.05)
    item["persistence_count_365d"] = firms_service.fetch_historical_count(lat, lon, 365, radius_deg=0.05)
    return item


@app.get("/api/hotspots")
def get_active_hotspots():
    try:
        raw_anomalies = firms_service.fetch_live_thermal_anomalies()
        processed = []
        for item in raw_anomalies:
            item = _attach_live_history(item)
            # Cluster size is calculated from the live FIRMS response: number
            # of detections within 1 km of this detection.
            item["cluster_size"] = sum(
                1 for other in raw_anomalies
                if haversine_distance(
                    float(item["lat"]), float(item["lon"]),
                    float(other["lat"]), float(other["lon"])
                ) <= 1000.0
            )
            processed.append(spatial_service.process_hotspot(item))
        return processed
    except (FirmsConfigurationError, OsmDataError, SentinelDataError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _find_nearest_firms(lat: float, lon: float, radius_km: float) -> Dict[str, Any]:
    """Find a real FIRMS observation near a custom coordinate."""
    # Use the current India feed and select the closest real detection.
    candidates = firms_service.fetch_live_thermal_anomalies(days=1)
    radius_m = radius_km * 1000
    from services.osm_service import haversine_distance
    nearby = []
    for item in candidates:
        d = haversine_distance(lat, lon, float(item["lat"]), float(item["lon"]))
        if d <= radius_m:
            nearby.append((d, item))
    if not nearby:
        raise HTTPException(
            status_code=404,
            detail=f"No live NASA FIRMS detection was found within {radius_km:.1f} km of this coordinate. No synthetic thermal observation was created.",
        )
    return min(nearby, key=lambda x: x[0])[1]


@app.post("/api/analyze-point")
def analyze_custom_coordinate(point: CustomPointAnalysis):
    try:
        real_detection = _find_nearest_firms(point.lat, point.lon, point.search_radius_km)
        real_detection["analysis_type"] = "USER_SELECTED_COORDINATE_USING_NEAREST_LIVE_FIRMS_DETECTION"
        real_detection["selected_coordinate"] = {"lat": point.lat, "lon": point.lon}
        real_detection = _attach_live_history(real_detection)
        live_points = firms_service.fetch_live_thermal_anomalies(days=1)
        real_detection["cluster_size"] = sum(
            1 for other in live_points
            if haversine_distance(
                float(real_detection["lat"]), float(real_detection["lon"]),
                float(other["lat"]), float(other["lon"])
            ) <= 1000.0
        )
        return spatial_service.process_hotspot(real_detection)
    except HTTPException:
        raise
    except (FirmsConfigurationError, OsmDataError, SentinelDataError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/sentinel/evidence")
def get_satellite_evidence(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    acq_date: Optional[str] = Query(None),
):
    try:
        osm_ctx = osm_service.query_infrastructure_context(lat, lon)
        evidence = sentinel_service.get_multi_sensor_evidence(
            lat, lon, is_industrial_nearby=osm_ctx["dist_to_industrial_m"] < 500, acq_date=acq_date
        )
        return {
            "location": {"lat": lat, "lon": lon},
            "osm_infrastructure": osm_ctx["nearest_facility_name"],
            "distance_to_industry_m": osm_ctx["dist_to_industrial_m"],
            "sentinel_fusion": evidence,
        }
    except (OsmDataError, SentinelDataError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/emergency/trigger")
def trigger_emergency_sos(sos: SosRequest):
    """Generate a response simulation using live OSM resources.

    This endpoint does not claim to contact a real fire department or CAP
    broadcast system. It creates a tactical simulation dossier.
    """
    zone_a_radius_m = 500
    zone_b_radius_m = 2000
    try:
        osm_data = osm_service.query_infrastructure_context(sos.lat, sos.lon, radius_m=20000)
        wind = get_current_wind(sos.lat, sos.lon)
    except (OsmDataError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    now = datetime.now(timezone.utc).isoformat()
    incident_id = f"INC-SOS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{sos.facility_code}"
    civilian_alert = {
        "protocol": "CAP-v1.2 format (simulation)",
        "event": "CRITICAL INDUSTRIAL ACCIDENT / BLAST HAZARD",
        "urgency": "Immediate",
        "severity": "Extreme",
        "certainty": "Observed (operator reported)",
        "headline": f"MANDATORY EVACUATION ORDER: {sos.facility_name}",
        "instruction": (
            f"An abnormal {sos.hazard_type.replace('_', ' ')} has been reported at {sos.facility_name}. "
            f"Persons within {zone_a_radius_m}m should evacuate immediately; persons within "
            f"{zone_b_radius_m}m should follow local emergency instructions."
        ),
        "target_geofence": {"center": {"lat": sos.lat, "lon": sos.lon}, "radius_m": zone_a_radius_m},
    }
    fire_dispatch = {
        "cad_priority": "PRIORITY_1_TACTICAL (simulation)",
        "target_facility": sos.facility_name,
        "coordinates": {"lat": sos.lat, "lon": sos.lon},
        "hazard_type": sos.hazard_type,
        "dispatched_units": [
            "HAZMAT Response Unit (simulation)",
            "Foam Tender x 4 (simulation)",
            "Hydraulic Platform 55m (simulation)",
            "Advanced Life Support Ambulances x 2 (simulation)",
        ],
        "tactical_osm_resources": {
            "nearest_water_reservoir_or_feature": osm_data["nearest_water_source"],
            "water_distance_m": osm_data["water_distance_m"],
            "nearest_mapped_road": osm_data["nearest_road_name"],
            "nearest_mapped_road_distance_m": osm_data["nearest_road_distance_m"],
            "wind": wind,
        },
    }
    return {
        "status": "EMERGENCY_RESPONSE_SIMULATION_GENERATED",
        "timestamp": now,
        "incident_id": incident_id,
        "reported_by": sos.reported_by,
        "evacuation_zones": {"zone_a_mandatory_m": zone_a_radius_m, "zone_b_advisory_m": zone_b_radius_m},
        "civilian_broadcast": civilian_alert,
        "fire_department_dispatch": fire_dispatch,
    }


frontend_dir = os.path.join(os.path.dirname(backend_dir), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_frontend_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"), headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

    @app.get("/{filename:path}")
    def serve_frontend_file(filename: str):
        filepath = os.path.join(frontend_dir, filename)
        if os.path.exists(filepath):
            return FileResponse(filepath, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
        return FileResponse(os.path.join(frontend_dir, "index.html"), headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
