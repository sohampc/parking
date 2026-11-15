"""Real Sentinel-1/2 evidence using Microsoft Planetary Computer's public
catalogue and Sentinel assets.

The catalogue is public; asset files are signed at runtime by the Planetary
Computer SDK. No synthetic NDVI/NBR/VV/VH values are generated here.
"""

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.windows import Window

PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


class SentinelDataError(RuntimeError):
    pass


class SentinelService:
    def __init__(self):
        self.catalog = pystac_client.Client.open(PC_STAC_URL)
        self.lookback_days = int(os.getenv("SENTINEL_LOOKBACK_DAYS", "30"))
        self.window_radius = int(os.getenv("SENTINEL_SAMPLE_RADIUS_PIXELS", "2"))

    @staticmethod
    def _target_datetime(acq_date: Optional[str]) -> datetime:
        if acq_date:
            try:
                return datetime.fromisoformat(acq_date.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    def _search_item(self, collection: str, lat: float, lon: float, acq_date: Optional[str], max_cloud: Optional[float] = None):
        target = self._target_datetime(acq_date)
        start = target - timedelta(days=self.lookback_days)
        end = target + timedelta(days=self.lookback_days)
        kwargs: Dict[str, Any] = {
            "collections": [collection],
            "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "datetime": f"{start.isoformat()}/{end.isoformat()}",
            "limit": 20,
        }
        if max_cloud is not None:
            kwargs["query"] = {"eo:cloud_cover": {"lte": max_cloud}}
        items = list(self.catalog.search(**kwargs).items())
        if not items and max_cloud is not None:
            kwargs.pop("query", None)
            items = list(self.catalog.search(**kwargs).items())
        if not items:
            raise SentinelDataError(
                f"No {collection} scene found within {self.lookback_days} days of {target.date()} "
                f"at {lat:.5f},{lon:.5f}."
            )
        items.sort(key=lambda item: abs((item.datetime or target) - target))
        return items[0]

    @staticmethod
    def _sample(asset_href: str, lat: float, lon: float, radius: int = 2) -> float:
        signed = planetary_computer.sign(asset_href)
        with rasterio.open(signed) as ds:
            row, col = ds.index(lon, lat)
            r0 = max(0, row - radius)
            c0 = max(0, col - radius)
            r1 = min(ds.height, row + radius + 1)
            c1 = min(ds.width, col + radius + 1)
            arr = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0), masked=True).astype("float64")
            values = arr.compressed()
            if values.size == 0:
                raise SentinelDataError("Sentinel raster contains no valid pixel at the requested coordinate.")
            value = float(np.median(values))
            if not math.isfinite(value):
                raise SentinelDataError("Sentinel raster returned a non-finite pixel value.")
            return value

    def _sentinel2(self, lat: float, lon: float, acq_date: Optional[str]) -> Dict[str, Any]:
        item = self._search_item("sentinel-2-l2a", lat, lon, acq_date, max_cloud=80)
        props = item.properties
        try:
            red = self._sample(item.assets["B04"].href, lat, lon, self.window_radius)
            nir = self._sample(item.assets["B08"].href, lat, lon, self.window_radius)
            swir2 = self._sample(item.assets["B12"].href, lat, lon, self.window_radius)
        except KeyError as exc:
            raise SentinelDataError(f"Sentinel-2 scene {item.id} is missing required band {exc}.") from exc

        scale = float(props.get("s2:reflectance_conversion_factor", 1.0))
        red *= scale
        nir *= scale
        swir2 *= scale
        ndvi = (nir - red) / (nir + red) if (nir + red) else 0.0
        nbr = (nir - swir2) / (nir + swir2) if (nir + swir2) else 0.0
        cloud = float(props.get("eo:cloud_cover", 0.0))

        return {
            "mission": "Sentinel-2",
            "scene_id": item.id,
            "acquisition_time": (item.datetime or datetime.now(timezone.utc)).isoformat(),
            "spatial_resolution": "10m (B04/B08), 20m (B12)",
            "indices": {
                "NDVI": round(float(ndvi), 4),
                "NDVI_interpretation": "Vegetation-dominant" if ndvi >= 0.2 else "Low vegetation / built surface",
                "NBR": round(float(nbr), 4),
                "NBR_interpretation": "Lower NBR" if nbr < 0.1 else "Higher NBR",
            },
            "estimated_cloud_cover_percent": round(cloud, 2),
            "visual_context": "Derived from actual Sentinel-2 spectral bands B04/B08/B12",
            "data_source": "Microsoft Planetary Computer / Copernicus Sentinel-2 L2A",
        }

    def _sentinel1(self, lat: float, lon: float, acq_date: Optional[str]) -> Dict[str, Any]:
        item = self._search_item("sentinel-1-rtc", lat, lon, acq_date)
        try:
            vv_linear = self._sample(item.assets["vv"].href, lat, lon, self.window_radius)
            vh_linear = self._sample(item.assets["vh"].href, lat, lon, self.window_radius)
        except KeyError:
            # Fall back to GRD if RTC assets are unavailable for a catalogue item.
            item = self._search_item("sentinel-1-grd", lat, lon, acq_date)
            vv_linear = self._sample(item.assets["vv"].href, lat, lon, self.window_radius)
            vh_linear = self._sample(item.assets["vh"].href, lat, lon, self.window_radius)

        if vv_linear <= 0 or vh_linear <= 0:
            raise SentinelDataError(f"Sentinel-1 scene {item.id} returned invalid non-positive backscatter.")
        vv_db = 10.0 * math.log10(vv_linear)
        vh_db = 10.0 * math.log10(vh_linear)
        return {
            "mission": "Sentinel-1",
            "scene_id": item.id,
            "acquisition_time": (item.datetime or datetime.now(timezone.utc)).isoformat(),
            "radar_mode": "RTC / C-band SAR",
            "polarization": "VV + VH",
            "cloud_penetration_status": "All-weather SAR measurement",
            "backscatter_telemetry": {
                "VV_backscatter_dB": round(vv_db, 3),
                "VH_backscatter_dB": round(vh_db, 3),
                "polarization_ratio_VV_VH": round(vv_db - vh_db, 3),
            },
            "radar_structural_verdict": "Actual Sentinel-1 backscatter sampled at the hotspot coordinate",
            "data_source": "Microsoft Planetary Computer / Copernicus Sentinel-1",
        }

    def get_multi_sensor_evidence(
        self, lat: float, lon: float, is_industrial_nearby: bool = False, acq_date: Optional[str] = None
    ) -> Dict[str, Any]:
        s2 = self._sentinel2(lat, lon, acq_date)
        s1 = self._sentinel1(lat, lon, acq_date)
        return {
            "optical_sentinel2": s2,
            "radar_sentinel1": s1,
            "fusion_note": "Sentinel evidence is measured data; it is not converted into an arbitrary confidence bonus.",
        }


_sentinel_service: Optional[SentinelService] = None


def get_sentinel_service() -> SentinelService:
    global _sentinel_service
    if _sentinel_service is None:
        _sentinel_service = SentinelService()
    return _sentinel_service
