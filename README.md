# NTRO Thermal Anomaly & Industrial Fire Intelligence Platform
**Problem Statement SIH26162 — Smart India Hackathon 2026 (Software Edition)**

## Important data-integrity rule
This build does **not** fabricate FIRMS, OSM, Sentinel-1 or Sentinel-2 measurements.
If a required external data source is unavailable, the backend returns an explicit error
instead of silently substituting a made-up number.

## Live data pipeline
```text
NASA FIRMS (live thermal detections)
          |
          +---- historical FIRMS persistence (30d / 365d)
          |
          v
OpenStreetMap / Overpass (live spatial context)
          |
          v
Copernicus Sentinel-1 + Sentinel-2
(via Microsoft Planetary Computer assets)
          |
          v
Spatial intelligence packet
          |
          v
Random Forest classifier
          |
          v
Threat assessment + dashboard
```

### NASA FIRMS
A free FIRMS MAP_KEY is required for the FIRMS web services. The application reads it from
`.env` as `NASA_FIRMS_MAP_KEY` and never exposes it to the browser.

### Sentinel-1 / Sentinel-2
The backend searches the public Planetary Computer STAC catalogue and samples actual
Sentinel assets. Sentinel-2 NDVI/NBR are calculated from B04/B08/B12. Sentinel-1 VV/VH
are sampled from Sentinel-1 RTC/GRD assets and converted to dB.

No fixed values such as `-6.4 dB`, `-12.1 dB`, `0.08 NDVI`, or `850 m water distance`
are used as fallbacks.

### OSM
Infrastructure distances are calculated from live Overpass elements. If a requested
category is not mapped within the configured search radius, the backend raises an error
rather than inventing a distance.

### AI model
The included Random Forest is a functioning model, but its current training/validation
set is a generated scenario dataset. `/api/metrics` explicitly labels this limitation.
Real-world validation requires an independently labelled dataset of real observations.

### Emergency SOS
The SOS endpoint generates an evacuation/tactical **simulation dossier**. It does not
claim to contact a real fire department, mobile-cell broadcast service, or CAD system.
Water-source information in the dossier comes from live OSM.

## Setup
1. Copy `.env.example` to `.env`.
2. Obtain a free NASA FIRMS MAP_KEY from the official FIRMS site and put it in `.env`.
3. Install dependencies:
   `python -m pip install -r requirements.txt`
4. Start:
   `python run.py`
5. Open the local dashboard and `/docs`.

If FIRMS is not configured, the application intentionally shows **no synthetic detections**.
This is by design.
