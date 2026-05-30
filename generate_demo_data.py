# ============================================================
# generate_demo_data.py — Generator Data Sintetis
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================
"""
Generate data pelanggaran sintetis yang realistis untuk testing dashboard.

Usage:
    python generate_demo_data.py                    # 300 data, 30 hari
    python generate_demo_data.py --count 500        # 500 data
    python generate_demo_data.py --count 100 --days 7
    python generate_demo_data.py --reset            # Hapus data lama dulu
"""

import argparse
import random
import sqlite3
from datetime import datetime, timedelta

from config import CAMERA_LOCATIONS, VIOLATION_TYPES

# ============================================================
# KONSTANTA DISTRIBUSI REALISTIS
# ============================================================

VEHICLE_TYPES = ["car", "motorcycle", "bus", "truck", "bicycle"]
VEHICLE_WEIGHTS = [0.45, 0.35, 0.08, 0.09, 0.03]   # Mobil & motor dominan

# Distribusi jenis pelanggaran
VIOLATION_WEIGHTS = {
    "busway_violation":    0.35,
    "illegal_parking":     0.40,
    "bike_lane_violation": 0.15,
    "wrong_way":           0.10,
}

# Durasi parkir liar (detik) — distribusi lognormal
PARKING_DURATION_MEAN = 300   # 5 menit rata-rata
PARKING_DURATION_STD  = 180

# Jam peak traffic Jakarta (distribusi lebih realistis)
# Pagi: 07-09, Siang: 12-13, Sore: 16-20
HOUR_WEIGHTS = [
    0.5, 0.3, 0.2, 0.2, 0.2, 0.4,   # 00-05
    0.8, 2.5, 3.0, 1.8, 1.2, 1.5,   # 06-11
    1.8, 1.2, 1.0, 1.2, 2.5, 3.2,   # 12-17
    2.8, 1.8, 1.2, 0.9, 0.7, 0.6,   # 18-23
]

# Template plat nomor Jakarta & sekitarnya
PLATE_PREFIXES = [
    "B", "D", "F", "Z", "T", "A", "E",
]
PLATE_NUMBERS = [f"{random.randint(1000, 9999)}" for _ in range(200)]
PLATE_SUFFIXES = [
    "ABC", "BCD", "CDE", "DEF", "EFG", "FGH", "GHI", "HIJ",
    "IJK", "JKL", "KLM", "LMN", "MNO", "NOP", "OPQ", "PQR",
    "QRS", "RST", "STU", "TUV", "UVW", "VWX", "WXY", "XYZ",
    "AAA", "BBB", "CCC", "DDD", "EEE", "FFF",
]

ETL_STATUS_WEIGHTS = {
    "pending": 0.55,
    "issued":  0.35,
    "paid":    0.10,
}

ZONE_NAMES = {
    "busway_violation":    ["busway_sudirman", "busway_thamrin", "busway_gatot_sub"],
    "illegal_parking":     ["no_parking_zone", "yellow_line_zone", "sidewalk_zone"],
    "bike_lane_violation": ["bike_lane", "bike_lane_south"],
    "wrong_way":           ["one_way_zone", "contraflow_zone"],
}

# ============================================================
# HELPERS
# ============================================================

def random_plate() -> str:
    prefix = random.choice(PLATE_PREFIXES)
    number = random.randint(1000, 9999)
    suffix = random.choice(PLATE_SUFFIXES)
    return f"{prefix} {number} {suffix}"

def random_timestamp(days_back: int) -> str:
    """Timestamp acak dengan distribusi jam yang realistis."""
    now   = datetime.now()
    start = now - timedelta(days=days_back)
    # Random hari
    day_offset = random.uniform(0, days_back)
    base = start + timedelta(days=day_offset)

    # Random jam dengan bobot peak hour
    hour = random.choices(range(24), weights=HOUR_WEIGHTS)[0]
    minute  = random.randint(0, 59)
    second  = random.randint(0, 59)

    ts = base.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return ts.isoformat()

def random_duration(violation_type: str) -> float:
    """Durasi pelanggaran (detik) sesuai jenisnya."""
    if violation_type == "illegal_parking":
        dur = random.gauss(PARKING_DURATION_MEAN, PARKING_DURATION_STD)
        return max(30.0, round(dur, 1))
    elif violation_type == "busway_violation":
        return round(random.uniform(5.0, 120.0), 1)
    elif violation_type == "bike_lane_violation":
        return round(random.uniform(3.0, 60.0), 1)
    else:
        return round(random.uniform(2.0, 30.0), 1)

def random_coords(cam_id: str) -> tuple[float, float]:
    """Koordinat sedikit di-scatter dari posisi kamera."""
    cam   = CAMERA_LOCATIONS.get(cam_id, {"lat": -6.2088, "lon": 106.8456})
    lat   = cam["lat"] + random.uniform(-0.001, 0.001)
    lon   = cam["lon"] + random.uniform(-0.001, 0.001)
    return round(lat, 6), round(lon, 6)

# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_demo_data(count: int = 300, days_back: int = 30, reset: bool = False) -> int:
    """
    Generate data pelanggaran sintetis ke violations.db.

    Args:
        count:     Jumlah record yang dibuat.
        days_back: Rentang waktu ke belakang (hari).
        reset:     Hapus data lama sebelum generate.

    Returns:
        Jumlah record yang berhasil diinsert.
    """
    from database import DB_PATH, DatabaseManager

    # Init DB (buat tabel jika belum ada)
    db = DatabaseManager()

    conn = sqlite3.connect(DB_PATH)

    if reset:
        conn.execute("DELETE FROM violations")
        conn.execute("DELETE FROM etl_tickets")
        conn.commit()
        print(f"🗑️  Data lama dihapus.")

    camera_ids = list(CAMERA_LOCATIONS.keys())

    # Buat pool plat nomor — sebagian akan muncul berulang (recidivism)
    # 80% dari total kendaraan = plat unik, 20% = pelanggar berulang
    unique_pool  = [random_plate() for _ in range(int(count * 0.7))]
    repeat_pool  = [random_plate() for _ in range(max(10, int(count * 0.05)))]

    inserted = 0
    violations_to_insert = []

    print(f"⏳ Generating {count} violation records ({days_back} hari terakhir)...")

    for i in range(count):
        violation_type = random.choices(
            list(VIOLATION_WEIGHTS.keys()),
            weights=list(VIOLATION_WEIGHTS.values()),
        )[0]

        vehicle_type = random.choices(VEHICLE_TYPES, weights=VEHICLE_WEIGHTS)[0]
        cam_id       = random.choice(camera_ids)
        lat, lon     = random_coords(cam_id)
        ts           = random_timestamp(days_back)
        duration     = random_duration(violation_type)
        etl_status   = random.choices(
            list(ETL_STATUS_WEIGHTS.keys()),
            weights=list(ETL_STATUS_WEIGHTS.values()),
        )[0]

        # Pilih plat: 15% kemungkinan dari repeat pool
        if random.random() < 0.15 and repeat_pool:
            plate = random.choice(repeat_pool)
        else:
            plate = random.choice(unique_pool)

        zone = random.choice(ZONE_NAMES.get(violation_type, ["unknown_zone"]))

        violations_to_insert.append((
            ts,                              # timestamp
            cam_id,                          # camera_id
            i + 1,                           # track_id (simulasi)
            vehicle_type,                    # vehicle_type
            plate,                           # license_plate
            violation_type,                  # violation_type
            zone,                            # zone_name
            duration,                        # duration_seconds
            round(random.uniform(0.55, 0.99), 2),  # confidence
            lat,                             # latitude
            lon,                             # longitude
            None,                            # image_path
            etl_status,                      # etl_status
            None,                            # etl_ticket_id
        ))

    # Batch insert
    conn.executemany(
        """INSERT INTO violations
           (timestamp, camera_id, track_id, vehicle_type, license_plate,
            violation_type, zone_name, duration_seconds, confidence,
            latitude, longitude, image_path, etl_status, etl_ticket_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        violations_to_insert
    )
    conn.commit()
    inserted = len(violations_to_insert)

    # Generate tiket E-TLE untuk yang sudah "issued"
    issued_ids = conn.execute(
        "SELECT id FROM violations WHERE etl_status = 'issued' AND etl_ticket_id IS NULL"
    ).fetchall()

    tickets = []
    for row in issued_ids:
        vid = row[0]
        ticket_id = f"ETLE-DEMO-{datetime.now().strftime('%Y%m%d')}-{vid:05d}"
        due_date  = (datetime.now() + timedelta(days=14)).isoformat()
        tickets.append((ticket_id, vid, due_date))

    if tickets:
        conn.executemany(
            "UPDATE violations SET etl_ticket_id = ? WHERE id = ?",
            [(t[0], t[1]) for t in tickets]
        )
        conn.executemany(
            """INSERT OR IGNORE INTO etl_tickets
               (ticket_id, violation_id, due_date)
               VALUES (?, ?, ?)""",
            tickets
        )
        conn.commit()

    conn.close()
    return inserted


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary():
    from database import DB_PATH, get_statistics, get_violations_df
    stats = get_statistics(days_back=9999)
    df    = get_violations_df(days_back=9999)

    print("\n" + "=" * 50)
    print("📊 RINGKASAN DATA YANG DIGENERATE")
    print("=" * 50)
    print(f"  Total pelanggaran : {stats['total']:,}")
    print(f"  Plat unik         : {stats['unique_plates']:,}")
    print(f"  Rata-rata durasi  : {stats['avg_duration']:.0f} detik")
    print()
    print("  Jenis Pelanggaran:")
    for vt, cnt in stats["per_type"].items():
        bar = "█" * (cnt * 20 // max(stats["per_type"].values()))
        print(f"    {vt:<30} {cnt:>5}  {bar}")
    print()
    print("  Per Kamera:")
    for cam, cnt in stats["per_camera"].items():
        print(f"    {cam}  →  {cnt:>4} pelanggaran")
    print()
    print("  Status E-TLE:")
    for status, cnt in stats["etl_summary"].items():
        print(f"    {status:<12} {cnt:>4}")
    print("=" * 50)
    print()


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate data pelanggaran sintetis untuk testing"
    )
    parser.add_argument("--count", type=int, default=300,
                        help="Jumlah record (default: 300)")
    parser.add_argument("--days",  type=int, default=30,
                        help="Rentang hari ke belakang (default: 30)")
    parser.add_argument("--reset", action="store_true",
                        help="Hapus data lama sebelum generate")
    args = parser.parse_args()

    inserted = generate_demo_data(
        count=args.count,
        days_back=args.days,
        reset=args.reset,
    )

    print(f"✅ {inserted:,} pelanggaran berhasil digenerate!")
    print_summary()
    print("🚀 Jalankan dashboard:")
    print("   streamlit run dashboard.py")
