# ============================================================
# generate_demo_data.py — Generate sample violation data
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================
"""
Generator untuk sample data pelanggaran lalu lintas.
Digunakan untuk:
- Testing dashboard tanpa detector berjalan
- Demo / presentasi
- Load testing database

Usage:
    python generate_demo_data.py            # Default: 300 records, 30 hari terakhir
    python generate_demo_data.py 500 60     # Custom: 500 records, 60 hari
"""

import random
import sqlite3
from datetime import datetime, timedelta
import logging

from config import DB_PATH
from database import DatabaseManager

logger = logging.getLogger(__name__)

# ============================================================
# SAMPLE DATA POOLS
# ============================================================

VEHICLE_TYPES = ["car", "motorcycle", "bus", "truck", "bicycle"]

VIOLATION_TYPES = [
    "busway_violation",
    "bike_lane_violation",
    "illegal_parking",
    "wrong_way",
]

LICENSE_PLATES = [
    "B1234AA", "B5678BB", "B9012CC", "B3456DD", "B7890EE",
    "B1111FF", "B2222GG", "B3333HH", "B4444II", "B5555JJ",
    "B6666KK", "B7777LL", "B8888MM", "B9999NN", "B0000OO",
    "B1010PP", "B2020QQ", "B3030RR", "B4040SS", "B5050TT",
    "B6060UU", "B7070VV", "B8080WW", "B9090XX", "B0101YY",
]

ZONES = [
    "busway_sudirman",
    "bike_lane",
    "no_parking_zone",
]

CAMERAS = ["CAM_001", "CAM_002", "CAM_003", "CAM_004", "CAM_005"]

LATITUDES = [-6.2088, -6.1751, -6.2146, -6.2297, -6.1944]
LONGITUDES = [106.8456, 106.8650, 106.8451, 106.8295, 106.8229]

# ============================================================
# GENERATOR
# ============================================================

def generate_demo_data(count: int = 300, days_back: int = 30):
    """
    Generate sample violation records untuk testing.
    
    Args:
        count: Jumlah record yang akan dibuat
        days_back: Distribusi record dalam N hari terakhir
    """
    logger.info(f"Generating {count} demo records (last {days_back} days)...")
    
    db = DatabaseManager()
    
    now = datetime.now()
    violations = []
    
    for i in range(count):
        # Random timestamp dalam range
        days_offset = random.randint(0, max(1, days_back))
        hours_offset = random.randint(0, 23)
        minutes_offset = random.randint(0, 59)
        
        ts = now - timedelta(days=days_offset, hours=hours_offset, minutes=minutes_offset)
        
        # Random data
        camera_idx = random.randint(0, len(CAMERAS) - 1)
        camera_id = CAMERAS[camera_idx]
        
        vehicle_type = random.choice(VEHICLE_TYPES)
        violation_type = random.choice(VIOLATION_TYPES)
        zone_name = random.choice(ZONES)
        license_plate = random.choice(LICENSE_PLATES)
        
        duration = random.uniform(10, 300)  # 10-300 detik
        speed = random.uniform(20, 120)  # km/h
        confidence = random.uniform(0.75, 0.99)
        
        violations.append({
            "timestamp": ts.isoformat(),
            "camera_id": camera_id,
            "track_id": random.randint(1000, 9999),
            "vehicle_type": vehicle_type,
            "license_plate": license_plate,
            "violation_type": violation_type,
            "zone_name": zone_name,
            "duration_seconds": round(duration, 1),
            "speed_kmh": round(speed, 1),
            "confidence": round(confidence, 3),
            "latitude": LATITUDES[camera_idx],
            "longitude": LONGITUDES[camera_idx],
        })
    
    # Bulk insert
    for viol in violations:
        try:
            db.save_violation(viol)
        except Exception as e:
            logger.warning(f"Failed to insert record: {e}")
    
    stats = db.get_statistics(days_back=days_back)
    logger.info(f"✓ Demo data generated!")
    logger.info(f"  Total: {stats['total']} violations")
    logger.info(f"  Types: {stats['per_type']}")
    logger.info(f"  Unique plates: {stats['unique_plates']}")


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    generate_demo_data(count=count, days_back=days)
    print(f"\n✅ Demo data siap! Buka dashboard dengan:")
    print(f"   streamlit run dashboard.py")
