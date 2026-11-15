/**
 * NTRO SCIENTIFIC GEOSPATIAL MONITORING CONSOLE - FRONTEND SCRIPT
 * Autonomous connection to NASA FIRMS, OpenStreetMap (OSM), Sentinel-1/2,
 * and the Emergency Incident Dispatch System.
 */

// Global State
let map = null;
let currentBasemap = null;
let markerLayerGroup = null;
let osmLayerGroup = null;
let evacuationLayerGroup = null;
let allHotspots = [];
let selectedHotspot = null;
let activeSosIncident = null;

// Backend API Base URL (connects automatically whether served from FastAPI or opened as file://)
const API_BASE = (window.location.protocol === 'file:' || !window.location.port) ? 'http://127.0.0.1:8000' : '';

// Tile Layer URLs
const TILE_LAYERS = {
  dark: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }),
  osm: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }),
  satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    maxZoom: 18
  })
};

// Fire Category Styling Definitions
const FIRE_CLASSES = {
  INDUSTRIAL_FIRE_HAZARD: {
    name: 'Industrial Fire Hazard',
    color: '#ef4444',
    threat: 'CRITICAL',
    badgeClass: 'threat-critical'
  },
  PERSISTENT_INDUSTRIAL_FLARE: {
    name: 'Persistent Industrial Flare',
    color: '#3b82f6',
    threat: 'ROUTINE',
    badgeClass: 'threat-low'
  },
  URBAN_RESIDENTIAL_FIRE: {
    name: 'Urban / Residential Fire',
    color: '#a855f7',
    threat: 'HIGH',
    badgeClass: 'threat-high'
  },
  FOREST_WILDFIRE: {
    name: 'Forest / Wildfire',
    color: '#22c55e',
    threat: 'HIGH',
    badgeClass: 'threat-high'
  },
  AGRICULTURAL_BURNING: {
    name: 'Agricultural Burning',
    color: '#f59e0b',
    threat: 'MODERATE',
    badgeClass: 'threat-high'
  }
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  initClocks();
  initEventListeners();
  loadHotspots();
});

// 1. Initialize Map
function initMap() {
  map = L.map('gis-map', {
    center: [20.5937, 78.9629], // Center on India
    zoom: 5,
    zoomControl: true,
    doubleClickZoom: true // Standard GIS behavior: double click zooms in
  });

  currentBasemap = TILE_LAYERS.dark;
  currentBasemap.addTo(map);

  osmLayerGroup = L.layerGroup().addTo(map);
  markerLayerGroup = L.layerGroup().addTo(map);
  evacuationLayerGroup = L.layerGroup().addTo(map);

  // NOTE: No map click handlers that create dots! Fires are detected autonomously by satellites.
}

// 2. Clocks
function initClocks() {
  function updateClocks() {
    const now = new Date();
    document.getElementById('utc-clock').textContent = now.toUTCString().slice(17, 25) + ' UTC';
    document.getElementById('ist-clock').textContent = now.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }) + ' IST';
  }
  updateClocks();
  setInterval(updateClocks, 1000);
}

// 3. Load & Render Hotspots from Live Backend Pipeline
function loadHotspots() {
  const statusEl = document.getElementById('feed-status-val');
  if (statusEl) {
    statusEl.textContent = "● CONNECTING TO LIVE PIPELINE...";
    statusEl.className = "metric-val";
  }

  fetch(`${API_BASE}/api/hotspots`, { cache: 'no-store' })
    .then(res => res.json().then(data => ({ ok: res.ok, status: res.status, data })))
    .then(({ ok, status, data }) => {
      if (!ok) {
        throw new Error(data?.detail || `API returned ${status}`);
      }
      if (!Array.isArray(data)) {
        throw new Error("Backend returned an invalid hotspot payload.");
      }
      allHotspots = data;
      if (statusEl) {
        statusEl.textContent = `● LIVE FIRMS + OSM + SENTINEL: ${data.length} DETECTIONS`;
        statusEl.className = "metric-val status-ok";
      }
      applyFilters(true);
    })
    .catch(err => {
      console.error("Live pipeline failed:", err);
      allHotspots = [];
      renderMarkers([]);
      document.getElementById('dossier-empty').classList.remove('hidden');
      document.getElementById('dossier-content').classList.add('hidden');
      if (statusEl) {
        statusEl.textContent = "● LIVE DATA UNAVAILABLE — NO SYNTHETIC DETECTIONS";
        statusEl.className = "metric-val status-error";
      }
    });
}

function renderMarkers(hotspots) {
  markerLayerGroup.clearLayers();
  osmLayerGroup.clearLayers();
  
  let criticalCount = 0;

  hotspots.forEach(item => {
    const conf = FIRE_CLASSES[item.classification] || FIRE_CLASSES.INDUSTRIAL_FIRE_HAZARD;
    if (item.threat_level === 'CRITICAL') criticalCount++;

    // 1. Render Satellite Thermal Anomaly Point
    const marker = L.circleMarker([item.lat, item.lon], {
      radius: 9,
      fillColor: conf.color,
      color: '#ffffff',
      weight: 1.5,
      opacity: 1,
      fillOpacity: 0.9
    });

    marker.on('click', () => {
      selectHotspot(item);
      map.setView([item.lat, item.lon], 13, { animate: true });
    });

    marker.bindTooltip(`
      <strong>${conf.name}</strong><br/>
      Location: <strong>${item.facility_name}</strong><br/>
      AI Confidence: <strong>${item.confidence_percent}%</strong><br/>
      Threat: <strong>${item.threat_level}</strong>
    `, { direction: 'top', offset: [0, -6] });

    markerLayerGroup.addLayer(marker);

    // 2. Render OpenStreetMap Infrastructure Perimeter (OSM Layer)
    if (item.dist_industrial_m <= 500 && item.facility_name && !item.facility_name.includes("None")) {
      const osmBuffer = L.circle([item.lat, item.lon], {
        radius: Math.max(150, item.dist_industrial_m + 50),
        color: '#38bdf8',
        weight: 1,
        dashArray: '3, 4',
        fillColor: '#38bdf8',
        fillOpacity: 0.08
      }).bindTooltip(`🏭 OSM Infrastructure: ${item.facility_name}`, { permanent: false, direction: 'bottom' });
      
      osmLayerGroup.addLayer(osmBuffer);
    }
  });

  // Update HUD
  document.getElementById('hud-total-count').textContent = hotspots.length;
  document.getElementById('hud-critical-count').textContent = criticalCount;
}

// 4. Select Hotspot & Populate Dossier
function selectHotspot(item) {
  selectedHotspot = item;

  document.getElementById('dossier-empty').classList.add('hidden');
  document.getElementById('dossier-content').classList.remove('hidden');

  document.getElementById('dossier-id').textContent = item.id;

  // Primary Verdict
  const conf = FIRE_CLASSES[item.classification] || FIRE_CLASSES.INDUSTRIAL_FIRE_HAZARD;
  document.getElementById('verdict-class-name').textContent = conf.name;
  
  const badge = document.getElementById('verdict-threat-badge');
  badge.textContent = item.threat_level;
  badge.className = `threat-badge ${conf.badgeClass}`;

  document.getElementById('verdict-confidence-pct').textContent = `${item.confidence_percent}%`;
  document.getElementById('verdict-conf-bar').style.width = `${item.confidence_percent}%`;

  // Probability Breakdown List across all 5 classes
  const probList = document.getElementById('probability-breakdown-list');
  probList.innerHTML = '';
  
  if (item.probabilities) {
    Object.entries(item.probabilities).forEach(([className, prob]) => {
      const probItem = document.createElement('div');
      probItem.className = 'prob-item';
      probItem.innerHTML = `
        <div class="prob-meta">
          <span>${className}</span>
          <span class="mono bold">${prob}%</span>
        </div>
        <div class="prob-bar-bg">
          <div class="prob-bar-fill" style="width: ${prob}%; background-color: ${prob > 50 ? '#38bdf8' : '#64748b'};"></div>
        </div>
      `;
      probList.appendChild(probItem);
    });
  }

  // Geolocation & OSM Metadata
  document.getElementById('meta-coords').textContent = `${item.lat.toFixed(4)}° N, ${item.lon.toFixed(4)}° E`;
  document.getElementById('meta-region').textContent = item.region;
  document.getElementById('meta-facility').textContent = item.facility_name;
  document.getElementById('meta-dist-ind').textContent = `${item.dist_industrial_m} meters`;
  document.getElementById('meta-dist-res').textContent = `${item.dist_residential_m} meters`;

  // Historical Recurrence
  document.getElementById('meta-p30').textContent = `${item.persistence_30d} detections`;
  document.getElementById('meta-p365').textContent = `${item.persistence_365d} detections`;
  document.getElementById('meta-recurrence-verdict').textContent = item.recurrence_evaluation;

  // Raw NASA FIRMS Sensor Telemetry
  document.getElementById('meta-sensor').textContent = item.sensor;
  document.getElementById('meta-time').textContent = item.acq_time;
  document.getElementById('meta-brightness').textContent = `${item.brightness_k} K (${(item.brightness_k - 273.15).toFixed(1)}° C)`;
  document.getElementById('meta-frp').textContent = `${item.frp_mw} MW`;
  document.getElementById('meta-daynight').textContent = item.daynight;

  // Populate only actual Sentinel-1 & Sentinel-2 evidence. No made-up fallbacks.
  const satEv = item.satellite_evidence;
  const s2 = satEv?.optical_sentinel2;
  const s1 = satEv?.radar_sentinel1;
  if (!s2 || !s1) {
    throw new Error("Backend returned a hotspot without complete Sentinel evidence.");
  }
  document.getElementById('meta-sentinel2-context').textContent = s2.visual_context;
  document.getElementById('meta-ndvi').textContent = `${s2.indices.NDVI} (${s2.indices.NDVI_interpretation})`;
  document.getElementById('meta-nbr').textContent = `${s2.indices.NBR} (${s2.indices.NBR_interpretation})`;
  document.getElementById('meta-sar-cloud').textContent = s1.cloud_penetration_status;
  const bsc = s1.backscatter_telemetry;
  document.getElementById('meta-sar-db').textContent = `VV: ${bsc.VV_backscatter_dB} dB | VH: ${bsc.VH_backscatter_dB} dB`;
  document.getElementById('meta-sar-verdict').textContent = s1.radar_structural_verdict;

  document.getElementById('action-recommendation-text').textContent = item.action_text;
}

// 5. Apply Filters
function applyFilters(autoSelectFirst = false) {
  const region = document.getElementById('filter-region').value;
  const fireClass = document.getElementById('filter-class').value;
  const minConf = parseFloat(document.getElementById('filter-confidence').value);
  const sensorSource = document.querySelector('input[name="sensor-source"]:checked').value;

  let filtered = allHotspots.filter(item => {
    if (item.confidence_percent < minConf) return false;
    if (fireClass !== 'ALL' && item.classification !== fireClass) return false;
    if (sensorSource !== 'ALL' && !item.sensor.includes(sensorSource)) return false;

    if (region === 'MAHARASHTRA_TROMBAY' && !item.region.includes('Mumbai')) return false;
    if (region === 'GUJARAT_JAMNAGAR' && !item.region.includes('Jamnagar')) return false;
    if (region === 'GUJARAT_ANKLESHWAR' && !item.region.includes('Ankleshwar')) return false;
    if (region === 'ODISHA_PARADIP' && !item.region.includes('Paradip')) return false;
    if (region === 'PUNJAB_AGRICULTURE' && !item.region.includes('Punjab')) return false;
    if (region === 'UTTARAKHAND_FOREST' && !item.region.includes('Uttarakhand')) return false;

    return true;
  });

  renderMarkers(filtered);

  // Automatically select the first critical detection on load so dossier is populated immediately
  if (autoSelectFirst && filtered.length > 0) {
    const firstCritical = filtered.find(h => h.threat_level === 'CRITICAL') || filtered[0];
    selectHotspot(firstCritical);
    map.setView([firstCritical.lat, firstCritical.lon], 11, { animate: false });
  }
}

// 6. Emergency SOS & Two-Channel Dispatch Trigger
async function triggerEmergencySos() {
  const facilityCode = document.getElementById('sos-facility').value;
  const hazardType = document.getElementById('sos-hazard').value;

  const facilityData = {
    'FAC-01': { name: 'BPCL Refinery Trombay (Mumbai)', lat: 19.0125, lon: 72.8942, region: 'Trombay, Mumbai' },
    'FAC-02': { name: 'Reliance Petrochemical Complex (Jamnagar)', lat: 22.3610, lon: 69.8732, region: 'Jamnagar, Gujarat' },
    'FAC-03': { name: 'Ankleshwar Chemical Unit #4 (Gujarat)', lat: 21.6140, lon: 72.9980, region: 'Ankleshwar GIDC' },
    'FAC-04': { name: 'Indian Oil Refinery (Paradip)', lat: 20.2850, lon: 86.6720, region: 'Paradip Port' }
  }[facilityCode];

  try {
    const res = await fetch(`${API_BASE}/api/emergency/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        facility_code: facilityCode,
        facility_name: facilityData.name,
        hazard_type: hazardType,
        lat: facilityData.lat,
        lon: facilityData.lon,
        reported_by: 'Plant Safety Control Officer'
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail || `API returned ${res.status}`);
    activeSosIncident = data;

    evacuationLayerGroup.clearLayers();
    const zoneA = L.circle([facilityData.lat, facilityData.lon], {
      radius: data.evacuation_zones.zone_a_mandatory_m,
      color: '#ef4444', weight: 2, fillColor: '#ef4444', fillOpacity: 0.35
    }).bindTooltip("ZONE A: Mandatory Evacuation Simulation (500m)", { permanent: true, direction: "center" });
    const zoneB = L.circle([facilityData.lat, facilityData.lon], {
      radius: data.evacuation_zones.zone_b_advisory_m,
      color: '#f59e0b', weight: 1.5, dashArray: '5, 5', fillColor: '#f59e0b', fillOpacity: 0.12
    }).bindTooltip("ZONE B: Advisory Simulation (2000m)", { permanent: false });
    const sosMarker = L.marker([facilityData.lat, facilityData.lon]).bindPopup(`
      <strong>🚨 EMERGENCY RESPONSE SIMULATION</strong><br/>
      Facility: <strong>${facilityData.name}</strong><br/>
      Hazard: <strong>${hazardType.replace('_', ' ')}</strong><br/>
      Status: <strong>TACTICAL DOSSIER GENERATED</strong><br/>
      Civilian Alert: <strong>CAP FORMAT GENERATED — NOT BROADCAST</strong>
    `);
    evacuationLayerGroup.addLayer(zoneA);
    evacuationLayerGroup.addLayer(zoneB);
    evacuationLayerGroup.addLayer(sosMarker);
    map.setView([facilityData.lat, facilityData.lon], 14, { animate: true });
    sosMarker.openPopup();

    const banner = document.getElementById('sos-active-banner');
    document.getElementById('sos-banner-text').textContent =
      `Facility: ${facilityData.name} | Zone A Simulation Active | Response Plan Generated`;
    banner.classList.remove('hidden');

    const water = data.fire_department_dispatch.tactical_osm_resources;
    alert(`🚨 [EMERGENCY RESPONSE SIMULATION]\n\n` +
      `Incident: ${data.incident_id}\n` +
      `Nearest mapped water feature: ${water.nearest_water_reservoir_or_feature}\n` +
      `Distance: ${water.water_distance_m} m\n\n` +
      `No real fire department or civilian broadcast was contacted.`);
  } catch (err) {
    console.error(err);
    alert(`Emergency simulation could not be generated.\n\n${err.message}`);
  }
}

// 7. Event Listeners
function initEventListeners() {
  document.getElementById('filter-region').addEventListener('change', () => applyFilters(false));
  document.getElementById('filter-class').addEventListener('change', () => applyFilters(false));
  
  const confSlider = document.getElementById('filter-confidence');
  confSlider.addEventListener('input', (e) => {
    document.getElementById('confidence-val').textContent = `${e.target.value}%`;
    applyFilters(false);
  });

  document.querySelectorAll('input[name="sensor-source"]').forEach(el => {
    el.addEventListener('change', () => applyFilters(false));
  });

  document.getElementById('basemap-selector').addEventListener('change', (e) => {
    const selected = e.target.value;
    map.removeLayer(currentBasemap);
    currentBasemap = TILE_LAYERS[selected] || TILE_LAYERS.dark;
    currentBasemap.addTo(map);
  });

  document.getElementById('btn-refresh-feed').addEventListener('click', () => {
    loadHotspots();
  });

  document.getElementById('btn-trigger-sos').addEventListener('click', () => {
    const confirmTrigger = confirm("CONFIRM EMERGENCY RESPONSE SIMULATION?\n\nThis creates evacuation zones and a tactical response dossier; it does not contact real responders.");
    if (confirmTrigger) {
      triggerEmergencySos();
    }
  });

  document.getElementById('btn-dismiss-sos').addEventListener('click', () => {
    evacuationLayerGroup.clearLayers();
    document.getElementById('sos-active-banner').classList.add('hidden');
    activeSosIncident = null;
  });

  document.getElementById('btn-dispatch-fire').addEventListener('click', () => {
    if (!selectedHotspot) return;
    alert(`🚒 [FIRE DISPATCH SIMULATION]\n\nEvent: ${selectedHotspot.id}\nLocation: ${selectedHotspot.region}\nFacility: ${selectedHotspot.facility_name}\nStatus: Tactical response plan generated; no real dispatch was sent.`);
  });

  document.getElementById('btn-alert-civilians').addEventListener('click', () => {
    if (!selectedHotspot) return;
    alert(`📢 [CIVILIAN ALERT SIMULATION]\n\nTarget Geofence: 1.5km radius around ${selectedHotspot.facility_name}\nAlert: CAP-format advisory generated; no mobile broadcast was sent.`);
  });

  document.getElementById('btn-export-dossier').addEventListener('click', () => {
    if (!selectedHotspot) return;
    const jsonStr = JSON.stringify(selectedHotspot, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `NTRO_DOSSIER_${selectedHotspot.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });
}
