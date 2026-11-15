"""NASA FIRMS live thermal anomaly service.

There is intentionally NO synthetic hotspot fallback in this service. If a
FIRMS MAP_KEY is not configured, the API fails clearly instead of displaying
made-up satellite detections.
"""

import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("firms_service")

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
INDIA_BBOX = "68,6.5,97.5,35.5"


class FirmsConfigurationError(RuntimeError):
    pass


class FirmsService:
    def __init__(self, map_key: Optional[str] = None):
        self.map_key = (map_key or os.getenv("NASA_FIRMS_MAP_KEY", "")).strip()
        self.timeout = int(os.getenv("FIRMS_TIMEOUT_SECONDS", "20"))

    def _require_key(self) -> None:
        if not self.map_key:
            raise FirmsConfigurationError(
                "NASA_FIRMS_MAP_KEY is not configured. Get a free FIRMS MAP_KEY "
                "from NASA FIRMS and put it in the backend environment."
            )

    def fetch_live_thermal_anomalies(
        self, sensor: str = "VIIRS_NOAA21_NRT", days: int = 1
    ) -> List[Dict[str, Any]]:
        self._require_key()
        days = max(1, min(int(days), 5))
        url = f"{FIRMS_BASE_URL}/{self.map_key}/{sensor}/{INDIA_BBOX}/{days}"
        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"NASA FIRMS request failed: {exc}") from exc

        if "latitude" not in resp.text or "longitude" not in resp.text:
            raise RuntimeError("NASA FIRMS returned an unexpected response.")

        records = self._parse_firms_csv(resp.text)
        logger.info("NASA FIRMS returned %d live detections", len(records))
        return records

    def fetch_historical_count(
        self,
        lat: float,
        lon: float,
        days: int,
        radius_deg: float = 0.05,
        sensor: str = "VIIRS_NOAA21_SP",
    ) -> int:
        """Count actual FIRMS detections around a point for a period.

        FIRMS limits an area request to five days, so a 30/365-day request is
        split into valid five-day chunks. Results are cached for the lifetime
        of the server process to avoid repeating expensive historical calls.
        """
        self._require_key()
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from datetime import date

        days = max(1, min(int(days), 365))
        cache_key = (round(lat, 5), round(lon, 5), days, round(radius_deg, 4), sensor)
        if not hasattr(self, "_history_cache"):
            self._history_cache = {}
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days - 1)
        chunk_starts = []
        cursor = start
        while cursor <= end:
            chunk_starts.append(cursor)
            cursor += timedelta(days=5)

        def fetch_chunk(chunk_start: date) -> int:
            chunk_days = min(5, (end - chunk_start).days + 1)
            bbox = f"{lon-radius_deg},{lat-radius_deg},{lon+radius_deg},{lat+radius_deg}"
            url = (
                f"{FIRMS_BASE_URL}/{self.map_key}/{sensor}/{bbox}/{chunk_days}/"
                f"{chunk_start.isoformat()}"
            )
            try:
                resp = requests.get(url, timeout=self.timeout)
                resp.raise_for_status()
                rows = self._parse_firms_csv(resp.text)
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"NASA FIRMS historical request failed for {chunk_start}: {exc}"
                ) from exc
            return sum(
                1
                for row in rows
                if abs(float(row["lat"]) - lat) <= radius_deg
                and abs(float(row["lon"]) - lon) <= radius_deg
            )

        total = 0
        # A small worker pool keeps the 365-day calculation practical while
        # remaining well below FIRMS' documented 5000-transactions/10-min limit.
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(fetch_chunk, d) for d in chunk_starts]
            for future in as_completed(futures):
                total += future.result()

        self._history_cache[cache_key] = total
        return total

    @staticmethod
    def _parse_firms_csv(csv_text: str) -> List[Dict[str, Any]]:
        reader = csv.DictReader(io.StringIO(csv_text))
        hotspots: List[Dict[str, Any]] = []
        for idx, row in enumerate(reader):
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                brightness = float(row.get("bright_ti4") or row.get("brightness") or 0)
                frp = float(row.get("frp") or 0)
                raw_conf = str(row.get("confidence", "")).strip().lower()
                if raw_conf in {"h", "high"}:
                    confidence = 90.0
                elif raw_conf in {"n", "nominal"}:
                    confidence = 70.0
                elif raw_conf in {"l", "low"}:
                    confidence = 30.0
                else:
                    try:
                        confidence = float(raw_conf)
                    except ValueError:
                        confidence = 0.0

                acq_date = row.get("acq_date") or ""
                acq_time_raw = str(row.get("acq_time") or "0000").zfill(4)
                acq_time = f"{acq_time_raw[:2]}:{acq_time_raw[2:]} UTC"
                satellite = row.get("satellite") or row.get("instrument") or "VIIRS"

                hotspots.append(
                    {
                        "id": f"FIRMS-{acq_date}-{acq_time_raw}-{idx+1:05d}",
                        "lat": lat,
                        "lon": lon,
                        "brightness": brightness,
                        "frp": frp,
                        "firms_confidence": confidence,
                        "acq_date": acq_date,
                        "acq_time": acq_time,
                        "satellite": satellite,
                        "daynight": "Night" if str(row.get("daynight", "")).upper() == "N" else "Day",
                    }
                )
            except (TypeError, ValueError, KeyError):
                continue
        return hotspots


_firms_service: Optional[FirmsService] = None


def get_firms_service(map_key: Optional[str] = None) -> FirmsService:
    global _firms_service
    if _firms_service is None:
        _firms_service = FirmsService(map_key)
    return _firms_service
