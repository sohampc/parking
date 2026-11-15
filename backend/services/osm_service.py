"""Live OpenStreetMap/Overpass spatial context service.

No fabricated distances are returned. A missing OSM category is treated as a
real data-quality problem and raises an error instead of inventing a distance.
"""

import math
import os
import requests
from typing import Dict, Any, List, Optional, Tuple

OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class OsmDataError(RuntimeError):
    pass


class OsmService:
    def __init__(self, timeout: int = 30):
        self.timeout = int(os.getenv("OVERPASS_TIMEOUT_SECONDS", str(timeout)))
        self._cache: Dict[str, Dict[str, Any]] = {}

    def query_infrastructure_context(self, lat: float, lon: float, radius_m: int = 20000) -> Dict[str, Any]:
        cache_key = f"{round(lat, 4)}_{round(lon, 4)}_{radius_m}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        query = f"""
        [out:json][timeout:{self.timeout}];
        (
          nwr["landuse"="industrial"](around:{radius_m},{lat},{lon});
          nwr["industrial"](around:{radius_m},{lat},{lon});
          nwr["man_made"="works"](around:{radius_m},{lat},{lon});
          nwr["power"="plant"](around:{radius_m},{lat},{lon});
          nwr["landuse"="residential"](around:{radius_m},{lat},{lon});
          nwr["place"="residential"](around:{radius_m},{lat},{lon});
          nwr["natural"="water"](around:{radius_m},{lat},{lon});
          nwr["waterway"](around:{radius_m},{lat},{lon});
          nwr["landuse"="forest"](around:{radius_m},{lat},{lon});
          nwr["natural"="wood"](around:{radius_m},{lat},{lon});
          nwr["landuse"="farmland"](around:{radius_m},{lat},{lon});
          nwr["landuse"="farm"](around:{radius_m},{lat},{lon});
          nwr["crop"](around:{radius_m},{lat},{lon});
          nwr["emergency"="fire_hydrant"](around:{radius_m},{lat},{lon});
          way["highway"](around:{radius_m},{lat},{lon});
        );
        out center tags;
        """
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=self.timeout + 5)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
        except (requests.RequestException, ValueError) as exc:
            raise OsmDataError(f"OpenStreetMap Overpass query failed: {exc}") from exc

        result = self._process_results(lat, lon, elements, radius_m)
        self._cache[cache_key] = result
        return result

    def _process_results(self, lat: float, lon: float, elements: List[Dict[str, Any]], radius_m: int) -> Dict[str, Any]:
        best: Dict[str, Tuple[float, Optional[str], str]] = {}
        nearest_road: Optional[Tuple[float, Optional[str]]] = None
        for el in elements:
            center = el.get("center", {})
            el_lat = el.get("lat", center.get("lat"))
            el_lon = el.get("lon", center.get("lon"))
            if el_lat is None or el_lon is None:
                continue
            tags = el.get("tags", {})
            dist = haversine_distance(lat, lon, float(el_lat), float(el_lon))
            if "highway" in tags and (nearest_road is None or dist < nearest_road[0]):
                nearest_road = (dist, tags.get("name") or tags.get("ref") or tags.get("highway"))
            if dist > radius_m:
                continue

            name = tags.get("name")
            is_ind = (
                tags.get("landuse") == "industrial"
                or "industrial" in tags
                or tags.get("man_made") == "works"
                or tags.get("power") == "plant"
            )
            is_res = tags.get("landuse") == "residential" or tags.get("place") == "residential"
            is_water = tags.get("natural") == "water" or "waterway" in tags or tags.get("emergency") == "fire_hydrant"
            is_forest = tags.get("landuse") == "forest" or tags.get("natural") == "wood"
            is_agri = tags.get("landuse") in {"farmland", "farm"} or "crop" in tags

            for category, condition in (
                ("industrial", is_ind),
                ("residential", is_res),
                ("water", is_water),
                ("forest", is_forest),
                ("agriculture", is_agri),
            ):
                if condition and (category not in best or dist < best[category][0]):
                    best[category] = (dist, name, el.get("type", "OSM"))

        required = ["industrial", "residential", "water", "forest", "agriculture"]
        missing = [c for c in required if c not in best]
        if missing:
            raise OsmDataError(
                "OSM has no mapped feature for: " + ", ".join(missing) +
                f" within {radius_m/1000:.0f} km of {lat:.5f},{lon:.5f}. "
                "No artificial distance was substituted."
            )

        if nearest_road is None:
            raise OsmDataError(
                f"OSM has no mapped road within {radius_m/1000:.0f} km of {lat:.5f},{lon:.5f}."
            )

        ind = best["industrial"]
        res = best["residential"]
        water = best["water"]
        forest = best["forest"]
        agri = best["agriculture"]
        return {
            "source": "OpenStreetMap (Overpass Live)",
            "dist_to_industrial_m": round(ind[0], 1),
            "nearest_facility_name": ind[1] or "Mapped industrial facility",
            "dist_to_residential_m": round(res[0], 1),
            "dist_to_forest_m": round(forest[0], 1),
            "dist_to_agriculture_m": round(agri[0], 1),
            "nearest_water_source": water[1] or "Mapped water feature",
            "water_distance_m": round(water[0], 1),
            "osm_radius_m": radius_m,
            "nearest_road_name": nearest_road[1] if nearest_road else "Mapped road",
            "nearest_road_distance_m": round(nearest_road[0], 1),
        }


_osm_service: Optional[OsmService] = None


def get_osm_service() -> OsmService:
    global _osm_service
    if _osm_service is None:
        _osm_service = OsmService()
    return _osm_service
