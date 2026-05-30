# sample_violations.py - Sample data untuk demo instant
import sqlite3
from datetime import datetime, timedelta
import random
from config import DB_PATH

def insert_sample_data():
    """Insert sample violations langsung ke database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Sample data (10 violations)
    sample_violations = [
        ("2026-05-30 08:15:30", "CAM_001", 1, "car", "B1234ABC", "busway_violation", "busway_sudirman", 45.5, "detected", None),
        ("2026-05-30 09:20:15", "CAM_002", 2, "motorcycle", "B5678DEF", "illegal_parking", "no_parking_zone", 120.0, "ticketed", "E-TLE-001"),
        ("2026-05-30 10:45:22", "CAM_001", 3, "car", "B9101GHI", "bike_lane_violation", "bike_lane", 30.0, "detected", None),
        ("2026-05-30 11:30:45", "CAM_003", 4, "motorcycle", "B1112JKL", "busway_violation", "busway_sudirman", 60.0, "detected", None),
        ("2026-05-30 13:15:10", "CAM_002", 5, "car", "B1314MNO", "illegal_parking", "no_parking_zone", 180.0, "ticketed", "E-TLE-002"),
        ("2026-05-30 14:22:30", "CAM_004", 6, "bus", "B1516PQR", "wrong_way", "busway_sudirman", 15.0, "detected", None),
        ("2026-05-30 15:10:55", "CAM_001", 7, "car", "B1718STU", "illegal_parking", "no_parking_zone", 240.0, "ticketed", "E-TLE-003"),
        ("2026-05-30 16:45:20", "CAM_005", 8, "motorcycle", "B1920VWX", "bike_lane_violation", "bike_lane", 25.0, "detected", None),
        ("2026-05-30 17:33:15", "CAM_002", 9, "car", "B2122YZA", "busway_violation", "busway_sudirman", 50.0, "detected", None),
        ("2026-05-30 18:20:40", "CAM_003", 10, "motorcycle", "B2324BCD", "illegal_parking", "no_parking_zone", 90.0, "ticketed", "E-TLE-004"),
    ]
    
    for violation in sample_violations:
        try:
            cursor.execute("""
                INSERT INTO violations 
                (timestamp, camera_id, track_id, vehicle_type, license_plate, violation_type, 
                 zone_name, duration_seconds, status, etl_ticket_id, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, violation + (0.95,))
        except sqlite3.IntegrityError:
            pass  # Skip jika sudah ada
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    insert_sample_data()
    print("✓ Sample data inserted")
