# ============================================================
# database.py — SQLite Database Manager
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================
"""
Modul ini mengelola semua operasi database SQLite:
- Inisialisasi schema
- Simpan & query pelanggaran
- Helper untuk dashboard & analytics
- E-TLE (Electronic Traffic Law Enforcement) management

Usage:
    from database import DatabaseManager, get_violations_df, get_statistics

    db = DatabaseManager()
    db.save_violation({...})
    df = get_violations_df()
"""

import sqlite3
import logging
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional

import pandas as pd

from config import DB_PATH

logger = logging.getLogger(__name__)

# ============================================================
# SCHEMA
# ============================================================

SCHEMA_SQL = """
-- Tabel utama pelanggaran lalu lintas
CREATE TABLE IF NOT EXISTS violations (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT     NOT NULL,                   -- ISO-8601
    camera_id         TEXT     NOT NULL DEFAULT 'CAM_001',
    track_id          INTEGER,                             -- ByteTrack ID
    vehicle_type      TEXT,                                -- car/motorcycle/bus/truck/bicycle
    license_plate     TEXT     DEFAULT 'UNKNOWN',
    violation_type    TEXT     NOT NULL,                   -- busway_violation / illegal_parking / ...
    zone_name         TEXT,
    duration_seconds  REAL     DEFAULT 0,
    speed_kmh         REAL     DEFAULT 0,                -- Estimasi kecepatan (km/h)
    confidence        REAL     DEFAULT 0.0,                -- Detection confidence (0–1)
    latitude          REAL,
    longitude         REAL,
    image_path        TEXT,                                -- Screenshot path (opsional)
    etl_status        TEXT     DEFAULT 'pending',          -- pending / issued / paid / cancelled
    etl_ticket_id     TEXT,
    status            TEXT     DEFAULT 'detected',
    created_at        TEXT     DEFAULT CURRENT_TIMESTAMP
);

-- Indeks untuk query umum
CREATE INDEX IF NOT EXISTS idx_violations_timestamp     ON violations(timestamp);
CREATE INDEX IF NOT EXISTS idx_violations_camera_id     ON violations(camera_id);
CREATE INDEX IF NOT EXISTS idx_violations_license_plate ON violations(license_plate);
CREATE INDEX IF NOT EXISTS idx_violations_violation_type ON violations(violation_type);
CREATE INDEX IF NOT EXISTS idx_violations_etl_status    ON violations(etl_status);

-- Tabel kamera
CREATE TABLE IF NOT EXISTS cameras (
    camera_id    TEXT PRIMARY KEY,
    name         TEXT,
    latitude     REAL,
    longitude    REAL,
    location     TEXT,
    is_active    INTEGER DEFAULT 1,
    added_at     TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- Tabel tiket E-TLE
CREATE TABLE IF NOT EXISTS etl_tickets (
    ticket_id       TEXT PRIMARY KEY,
    violation_id    INTEGER REFERENCES violations(id),
    license_plate   TEXT,
    violation_type  TEXT,
    issued_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    due_date        TEXT,
    fine_amount     INTEGER DEFAULT 500000,
    status          TEXT DEFAULT 'issued',
    notes           TEXT
);
"""

# ============================================================
# DATABASE MANAGER
# ============================================================

class DatabaseManager:
    """Manager utama untuk operasi database SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._seed_cameras()

    # ----------------------------------------------------------
    # Context manager untuk koneksi
    # ----------------------------------------------------------
    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")   # Better concurrency
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    # ----------------------------------------------------------
    # Inisialisasi schema
    # ----------------------------------------------------------
    def _init_db(self):
        """Buat tabel jika belum ada."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with self._get_conn() as conn:
            conn.executescript(SCHEMA_SQL)
        logger.info(f"Database ready: {self.db_path}")

    # ----------------------------------------------------------
    # Seed data kamera dari config
    # ----------------------------------------------------------
    def _seed_cameras(self):
        """Masukkan data kamera dari config.py jika belum ada."""
        try:
            from config import CAMERA_LOCATIONS
            with self._get_conn() as conn:
                for cam_id, info in CAMERA_LOCATIONS.items():
                    conn.execute(
                        """INSERT OR IGNORE INTO cameras
                           (camera_id, name, latitude, longitude, location)
                           VALUES (?, ?, ?, ?, ?)""",
                        (cam_id, info["name"], info["lat"], info["lon"], info["name"])
                    )
        except Exception as e:
            logger.warning(f"Seed cameras failed (non-critical): {e}")

    # ----------------------------------------------------------
    # SAVE VIOLATION
    # ----------------------------------------------------------
    def save_violation(self, data: dict) -> int:
        """
        Simpan satu record pelanggaran ke database.

        Args:
            data: dict dengan key:
                - timestamp (str, ISO-8601) — opsional, default now
                - camera_id (str)
                - track_id (int)
                - vehicle_type (str)
                - license_plate (str)
                - violation_type (str)
                - zone_name (str)
                - duration_seconds (float)
                - confidence (float)
                - latitude (float)
                - longitude (float)
                - image_path (str)

        Returns:
            ID baris yang baru diinsert.
        """
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO violations
                   (timestamp, camera_id, track_id, vehicle_type, license_plate,
                    violation_type, zone_name, duration_seconds, speed_kmh, confidence,
                    latitude, longitude, image_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("timestamp", now),
                    data.get("camera_id", "CAM_001"),
                    data.get("track_id"),
                    data.get("vehicle_type", "car"),
                    data.get("license_plate", "UNKNOWN"),
                    data.get("violation_type", "unknown"),
                    data.get("zone_name"),
                    data.get("duration_seconds", 0),
                    data.get("speed_kmh", 0),
                    data.get("confidence", 0.0),
                    data.get("latitude"),
                    data.get("longitude"),
                    data.get("image_path"),
                )
            )
            return cursor.lastrowid

    # ----------------------------------------------------------
    # GET VIOLATIONS
    # ----------------------------------------------------------
    def get_violations(
        self,
        days_back: int = 30,
        camera_id: Optional[str] = None,
        violation_type: Optional[str] = None,
        etl_status: Optional[str] = None,
        limit: int = 10_000,
    ) -> list[dict]:
        """
        Ambil data pelanggaran.

        Args:
            days_back: Ambil N hari terakhir (0 = semua).
            camera_id: Filter per kamera.
            violation_type: Filter per jenis pelanggaran.
            etl_status: Filter per status E-TLE.
            limit: Maksimum baris.

        Returns:
            List of dicts.
        """
        conditions = []
        params = []

        if days_back > 0:
            cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
            conditions.append("timestamp >= ?")
            params.append(cutoff)

        if camera_id:
            conditions.append("camera_id = ?")
            params.append(camera_id)

        if violation_type:
            conditions.append("violation_type = ?")
            params.append(violation_type)

        if etl_status:
            conditions.append("etl_status = ?")
            params.append(etl_status)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM violations {where} ORDER BY timestamp DESC LIMIT ?",
                params
            ).fetchall()
            return [dict(r) for r in rows]

    # ----------------------------------------------------------
    # GET AS DATAFRAME
    # ----------------------------------------------------------
    def get_violations_df(self, days_back: int = 30, **kwargs) -> pd.DataFrame:
        """Kembalikan data pelanggaran sebagai pandas DataFrame."""
        rows = self.get_violations(days_back=days_back, **kwargs)
        if not rows:
            return pd.DataFrame(columns=[
                "id", "timestamp", "camera_id", "track_id", "vehicle_type",
                "license_plate", "violation_type", "zone_name", "duration_seconds",
                "confidence", "latitude", "longitude", "image_path",
                "etl_status", "etl_ticket_id", "created_at"
            ])
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    # ----------------------------------------------------------
    # GET STATISTICS
    # ----------------------------------------------------------
    def get_statistics(self, days_back: int = 30) -> dict:
        """
        Hitung statistik ringkasan.

        Returns:
            dict: total, per_type, per_camera, per_vehicle, etl_summary
        """
        df = self.get_violations_df(days_back=days_back)

        if df.empty:
            return {
                "total": 0,
                "per_type": {},
                "per_camera": {},
                "per_vehicle": {},
                "etl_summary": {"pending": 0, "issued": 0, "paid": 0},
                "avg_duration": 0,
                "unique_plates": 0,
            }

        return {
            "total": len(df),
            "per_type": df["violation_type"].value_counts().to_dict(),
            "per_camera": df["camera_id"].value_counts().to_dict(),
            "per_vehicle": df["vehicle_type"].value_counts().to_dict(),
            "etl_summary": df["etl_status"].value_counts().to_dict(),
            "avg_duration": round(df["duration_seconds"].mean(), 1),
            "unique_plates": df["license_plate"].nunique(),
        }

    # ----------------------------------------------------------
    # E-TLE: GENERATE TICKET
    # ----------------------------------------------------------
    def generate_etl_ticket(self, violation_id: int) -> Optional[str]:
        """
        Buat tiket E-TLE untuk satu pelanggaran.

        Args:
            violation_id: ID baris di tabel violations.

        Returns:
            ticket_id (str) jika berhasil, None jika gagal.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM violations WHERE id = ?", (violation_id,)
            ).fetchone()

            if not row:
                logger.warning(f"Violation ID {violation_id} not found")
                return None

            if row["etl_status"] == "issued":
                logger.info(f"Ticket already issued for violation {violation_id}")
                return row["etl_ticket_id"]

            ticket_id = f"ETLE-{datetime.now().strftime('%Y%m%d%H%M%S')}-{violation_id:05d}"
            due_date  = (datetime.now() + timedelta(days=14)).isoformat()

            conn.execute(
                """INSERT INTO etl_tickets
                   (ticket_id, violation_id, license_plate, violation_type, due_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (ticket_id, violation_id, row["license_plate"],
                 row["violation_type"], due_date)
            )
            conn.execute(
                "UPDATE violations SET etl_status = 'issued', etl_ticket_id = ? WHERE id = ?",
                (ticket_id, violation_id)
            )
            logger.info(f"Ticket generated: {ticket_id}")
            return ticket_id

    # ----------------------------------------------------------
    # GET REPEAT OFFENDERS
    # ----------------------------------------------------------
    def get_repeat_offenders(self, days_back: int = 30, min_count: int = 2) -> pd.DataFrame:
        """
        Daftar pelanggar berulang.

        Args:
            days_back: Rentang waktu analisis.
            min_count: Minimum jumlah pelanggaran untuk masuk daftar.

        Returns:
            DataFrame dengan kolom: license_plate, count, last_violation, risk_level
        """
        df = self.get_violations_df(days_back=days_back)
        if df.empty:
            return pd.DataFrame()

        offenders = (
            df.groupby("license_plate")
            .agg(
                count=("id", "count"),
                last_violation=("timestamp", "max"),
                violation_types=("violation_type", lambda x: ", ".join(x.unique())),
            )
            .reset_index()
            .query("count >= @min_count")
            .sort_values("count", ascending=False)
        )

        def risk_level(n):
            if n >= 10: return "🔴 Tinggi"
            if n >= 5:  return "🟠 Sedang"
            return "🟡 Rendah"

        offenders["risk_level"] = offenders["count"].apply(risk_level)
        return offenders

    # ----------------------------------------------------------
    # DELETE OLD RECORDS
    # ----------------------------------------------------------
    def purge_old_records(self, older_than_days: int = 365):
        """Hapus record lebih lama dari N hari (maintenance)."""
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        with self._get_conn() as conn:
            result = conn.execute(
                "DELETE FROM violations WHERE timestamp < ?", (cutoff,)
            )
            logger.info(f"Purged {result.rowcount} records older than {older_than_days} days")

    # ----------------------------------------------------------
    # GET CAMERA LIST
    # ----------------------------------------------------------
    def get_cameras(self) -> list[dict]:
        """Ambil semua kamera dari database."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM cameras ORDER BY camera_id").fetchall()
            return [dict(r) for r in rows]


# ============================================================
# MODULE-LEVEL HELPERS (kompatibel dengan import di modul lain)
# ============================================================

_db: Optional[DatabaseManager] = None

def _get_db() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db


def save_violation(data: dict) -> int:
    """Shortcut: simpan pelanggaran."""
    return _get_db().save_violation(data)


def get_violations_df(days_back: int = 30, **kwargs) -> pd.DataFrame:
    """Shortcut: ambil DataFrame pelanggaran."""
    return _get_db().get_violations_df(days_back=days_back, **kwargs)


def get_statistics(days_back: int = 30) -> dict:
    """Shortcut: statistik ringkasan."""
    return _get_db().get_statistics(days_back=days_back)


def generate_etl_ticket(violation_id: int) -> Optional[str]:
    """Shortcut: buat tiket E-TLE."""
    return _get_db().generate_etl_ticket(violation_id)


def get_repeat_offenders(days_back: int = 30, min_count: int = 2) -> pd.DataFrame:
    """Shortcut: pelanggar berulang."""
    return _get_db().get_repeat_offenders(days_back=days_back, min_count=min_count)


# ============================================================
# STANDALONE — jalankan langsung untuk init + verifikasi
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    db = DatabaseManager()
    stats = db.get_statistics()

    print("\n✅ Database berhasil diinisialisasi!")
    print(f"   Path     : {DB_PATH}")
    print(f"   Total    : {stats['total']} pelanggaran")
    print(f"   Kamera   : {len(db.get_cameras())} terdaftar")
    print("\nSiap digunakan 🚀")
