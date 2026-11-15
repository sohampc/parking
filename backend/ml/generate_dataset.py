"""
Dataset Generator for NASA FIRMS Thermal Anomaly & Fire Classification
Generates a realistic, calibrated training dataset based on NASA VIIRS/MODIS thermal telemetry,
OpenStreetMap (OSM) spatial proximity, and historical persistence patterns across Indian scenarios.

Classes:
0 - INDUSTRIAL_FIRE_HAZARD (Uncontrolled accidental industrial fire)
1 - PERSISTENT_INDUSTRIAL_FLARE (Routine refinery flare, furnace, kiln)
2 - URBAN_RESIDENTIAL_FIRE (Structure/building fire in urban dense area)
3 - FOREST_WILDFIRE (Vegetation / wildland fire)
4 - AGRICULTURAL_BURNING (Crop residue / stubble burning)
"""

import numpy as np
import pandas as pd
import os

def generate_synthetic_thermal_dataset(n_samples_per_class=1200, random_state=42):
    np.random.seed(random_state)
    records = []

    # 1. INDUSTRIAL_FIRE_HAZARD (Accidental factory/refinery/chemical blast)
    # Characteristics: High temperature, very high FRP, low/zero history in 30/365 days, close to industrial OSM
    for _ in range(n_samples_per_class):
        brightness = np.random.normal(365, 20)          # Kelvin (high)
        frp = np.random.exponential(45) + 20             # Fire Radiative Power (MW)
        firms_conf = np.random.uniform(80, 100)          # Sensor confidence
        dist_industrial = np.random.uniform(10, 350)     # Inside or right next to industrial zone (meters)
        dist_residential = np.random.uniform(500, 3000)
        dist_forest = np.random.uniform(1500, 10000)
        dist_agriculture = np.random.uniform(1000, 8000)
        persistence_30d = np.random.choice([0, 1, 2], p=[0.85, 0.12, 0.03])  # Unprecedented!
        persistence_365d = np.random.choice([0, 1, 2, 3], p=[0.80, 0.14, 0.04, 0.02])
        is_night = np.random.choice([0, 1], p=[0.4, 0.6])
        cluster_size = np.random.randint(1, 6)

        records.append({
            "brightness": brightness,
            "frp": frp,
            "firms_confidence": firms_conf,
            "dist_to_industrial_m": dist_industrial,
            "dist_to_residential_m": dist_residential,
            "dist_to_forest_m": dist_forest,
            "dist_to_agriculture_m": dist_agriculture,
            "persistence_count_30d": persistence_30d,
            "persistence_count_365d": persistence_365d,
            "is_night": is_night,
            "cluster_size": cluster_size,
            "label": 0,
            "class_name": "INDUSTRIAL_FIRE_HAZARD"
        })

    # 2. PERSISTENT_INDUSTRIAL_FLARE (Routine flare stack, blast furnace, kiln)
    # Characteristics: Moderate/high temperature, stable FRP, HIGH 30d/365d persistence, right at industrial OSM
    for _ in range(n_samples_per_class):
        brightness = np.random.normal(350, 15)
        frp = np.random.normal(25, 8)
        firms_conf = np.random.uniform(75, 100)
        dist_industrial = np.random.uniform(5, 200)      # Directly inside refinery/plant
        dist_residential = np.random.uniform(800, 4000)
        dist_forest = np.random.uniform(2000, 12000)
        dist_agriculture = np.random.uniform(1000, 8000)
        persistence_30d = np.random.randint(12, 31)      # Burns almost daily!
        persistence_365d = np.random.randint(80, 340)    # Very high annual recurrence
        is_night = np.random.choice([0, 1], p=[0.45, 0.55])
        cluster_size = np.random.choice([1, 2], p=[0.85, 0.15])

        records.append({
            "brightness": brightness,
            "frp": max(5, frp),
            "firms_confidence": firms_conf,
            "dist_to_industrial_m": dist_industrial,
            "dist_to_residential_m": dist_residential,
            "dist_to_forest_m": dist_forest,
            "dist_to_agriculture_m": dist_agriculture,
            "persistence_count_30d": persistence_30d,
            "persistence_count_365d": persistence_365d,
            "is_night": is_night,
            "cluster_size": cluster_size,
            "label": 1,
            "class_name": "PERSISTENT_INDUSTRIAL_FLARE"
        })

    # 3. URBAN_RESIDENTIAL_FIRE (Building/house/slum fire in city)
    # Characteristics: Moderate/high temperature, concentrated, close to residential OSM, far from forest/agri
    for _ in range(n_samples_per_class):
        brightness = np.random.normal(345, 18)
        frp = np.random.exponential(20) + 10
        firms_conf = np.random.uniform(65, 95)
        dist_industrial = np.random.uniform(1500, 8000)
        dist_residential = np.random.uniform(10, 250)     # Inside dense urban area
        dist_forest = np.random.uniform(3000, 15000)
        dist_agriculture = np.random.uniform(2000, 10000)
        persistence_30d = np.random.choice([0, 1], p=[0.95, 0.05])  # Zero history
        persistence_365d = np.random.choice([0, 1], p=[0.92, 0.08])
        is_night = np.random.choice([0, 1], p=[0.5, 0.5])
        cluster_size = np.random.randint(1, 4)

        records.append({
            "brightness": brightness,
            "frp": frp,
            "firms_confidence": firms_conf,
            "dist_to_industrial_m": dist_industrial,
            "dist_to_residential_m": dist_residential,
            "dist_to_forest_m": dist_forest,
            "dist_to_agriculture_m": dist_agriculture,
            "persistence_count_30d": persistence_30d,
            "persistence_count_365d": persistence_365d,
            "is_night": is_night,
            "cluster_size": cluster_size,
            "label": 2,
            "class_name": "URBAN_RESIDENTIAL_FIRE"
        })

    # 4. FOREST_WILDFIRE (Simlipal, Uttarakhand, Western Ghats)
    # Characteristics: Spatially clustered, close to forest OSM, far from industrial/residential
    for _ in range(n_samples_per_class):
        brightness = np.random.normal(355, 22)
        frp = np.random.exponential(35) + 15
        firms_conf = np.random.uniform(70, 100)
        dist_industrial = np.random.uniform(5000, 30000)
        dist_residential = np.random.uniform(3000, 20000)
        dist_forest = np.random.uniform(0, 200)          # In forest cover
        dist_agriculture = np.random.uniform(1000, 15000)
        persistence_30d = np.random.choice([0, 1, 2, 3], p=[0.70, 0.18, 0.08, 0.04]) # Multiple days during wildfire
        persistence_365d = np.random.randint(0, 10)      # Occasional seasonal fire
        is_night = np.random.choice([0, 1], p=[0.6, 0.4])
        cluster_size = np.random.randint(3, 15)          # Wide spread cluster!

        records.append({
            "brightness": brightness,
            "frp": frp,
            "firms_confidence": firms_conf,
            "dist_to_industrial_m": dist_industrial,
            "dist_to_residential_m": dist_residential,
            "dist_to_forest_m": dist_forest,
            "dist_to_agriculture_m": dist_agriculture,
            "persistence_count_30d": persistence_30d,
            "persistence_count_365d": persistence_365d,
            "is_night": is_night,
            "cluster_size": cluster_size,
            "label": 3,
            "class_name": "FOREST_WILDFIRE"
        })

    # 5. AGRICULTURAL_BURNING (Punjab/Haryana stubble burning)
    # Characteristics: Moderate FRP, close to agricultural land, daytime predominance, clustered in rural regions
    for _ in range(n_samples_per_class):
        brightness = np.random.normal(335, 12)
        frp = np.random.exponential(12) + 5
        firms_conf = np.random.uniform(60, 90)
        dist_industrial = np.random.uniform(3000, 25000)
        dist_residential = np.random.uniform(1500, 12000)
        dist_forest = np.random.uniform(2000, 20000)
        dist_agriculture = np.random.uniform(0, 250)     # In agricultural field
        persistence_30d = np.random.choice([0, 1, 2], p=[0.80, 0.15, 0.05])
        persistence_365d = np.random.randint(1, 8)       # Seasonal stubble recurrence
        is_night = np.random.choice([0, 1], p=[0.8, 0.2])# Mostly daytime burns
        cluster_size = np.random.randint(1, 8)

        records.append({
            "brightness": brightness,
            "frp": frp,
            "firms_confidence": firms_conf,
            "dist_to_industrial_m": dist_industrial,
            "dist_to_residential_m": dist_residential,
            "dist_to_forest_m": dist_forest,
            "dist_to_agriculture_m": dist_agriculture,
            "persistence_count_30d": persistence_30d,
            "persistence_count_365d": persistence_365d,
            "is_night": is_night,
            "cluster_size": cluster_size,
            "label": 4,
            "class_name": "AGRICULTURAL_BURNING"
        })

    df = pd.DataFrame(records)
    # Shuffle
    df = df.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
    return df

if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "training_dataset.csv")
    df = generate_synthetic_thermal_dataset(n_samples_per_class=1500)
    df.to_csv(csv_path, index=False)
    print(f"Generated {len(df)} samples across 5 fire classes. Saved to {csv_path}")
    print(df["class_name"].value_counts())
