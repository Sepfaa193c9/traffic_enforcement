# ============================================================
# analytics.py — Fungsi Analitik Traffic Enforcement
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================
"""
Semua fungsi analitik yang digunakan oleh dashboard dan report generator.

Usage:
    from analytics import (
        get_peak_violation_hours,
        get_camera_hotspots,
        get_daily_trend,
        get_violation_summary,
        get_recidivism_analysis,
    )
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np

from database import get_violations_df, get_repeat_offenders

logger = logging.getLogger(__name__)

# ============================================================
# PEAK HOURS
# ============================================================

def get_peak_violation_hours(days_back: int = 30, top_n: int = 3) -> dict:
    """
    Temukan jam-jam dengan pelanggaran terbanyak.

    Returns:
        {
          "hourly_counts": {0: 5, 1: 3, ..., 23: 12},
          "peak_hours": [8, 17, 18],
          "peak_hour": 8,
          "off_peak_hour": 3,
        }
    """
    df = get_violations_df(days_back=days_back)
    if df.empty:
        return {"hourly_counts": {}, "peak_hours": [], "peak_hour": None, "off_peak_hour": None}

    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    hourly = df.groupby("hour").size()

    # Lengkapi semua jam 0-23
    full_hourly = {h: int(hourly.get(h, 0)) for h in range(24)}
    sorted_hours = sorted(full_hourly, key=full_hourly.get, reverse=True)

    return {
        "hourly_counts":  full_hourly,
        "peak_hours":     sorted_hours[:top_n],
        "peak_hour":      sorted_hours[0],
        "off_peak_hour":  sorted_hours[-1],
    }


# ============================================================
# CAMERA HOTSPOTS
# ============================================================

def get_camera_hotspots(days_back: int = 30) -> list[dict]:
    """
    Ranking kamera berdasarkan jumlah pelanggaran.

    Returns:
        List of dicts: [{camera_id, name, lat, lon, count, percentage}, ...]
    """
    from config import CAMERA_LOCATIONS

    df = get_violations_df(days_back=days_back)
    if df.empty:
        return []

    total = len(df)
    counts = df["camera_id"].value_counts()

    result = []
    for cam_id, info in CAMERA_LOCATIONS.items():
        count = int(counts.get(cam_id, 0))
        result.append({
            "camera_id":  cam_id,
            "name":       info["name"],
            "lat":        info["lat"],
            "lon":        info["lon"],
            "count":      count,
            "percentage": round(count / total * 100, 1) if total > 0 else 0,
        })

    return sorted(result, key=lambda x: x["count"], reverse=True)


# ============================================================
# DAILY TREND
# ============================================================

def get_daily_trend(days_back: int = 30) -> pd.DataFrame:
    """
    Tren pelanggaran harian.

    Returns:
        DataFrame kolom: date, count, busway, illegal_parking,
                         bike_lane, wrong_way, moving_avg_7d
    """
    df = get_violations_df(days_back=days_back)
    if df.empty:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["timestamp"]).dt.date

    # Total per hari
    daily = df.groupby("date").size().reset_index(name="count")

    # Per violation type per hari
    for vt in ["busway_violation", "illegal_parking", "bike_lane_violation", "wrong_way"]:
        sub = df[df["violation_type"] == vt].groupby("date").size()
        col = vt.replace("_violation", "").replace("_", "_")
        daily[col] = daily["date"].map(sub).fillna(0).astype(int)

    # 7-day moving average
    daily = daily.sort_values("date")
    daily["moving_avg_7d"] = daily["count"].rolling(7, min_periods=1).mean().round(1)

    return daily


# ============================================================
# VIOLATION SUMMARY
# ============================================================

def get_violation_summary(days_back: int = 30) -> dict:
    """
    Ringkasan komprehensif pelanggaran untuk laporan eksekutif.

    Returns:
        dict dengan semua metrik penting.
    """
    df = get_violations_df(days_back=days_back)

    if df.empty:
        return {
            "total": 0, "per_type": {}, "per_camera": {}, "per_vehicle": {},
            "avg_duration": 0, "max_duration": 0, "unique_plates": 0,
            "etl_issued": 0, "etl_pending": 0, "etl_paid": 0,
            "busiest_day": None, "busiest_hour": None,
            "top_offender_plate": None, "top_offender_count": 0,
        }

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"]      = df["timestamp"].dt.date
    df["hour"]      = df["timestamp"].dt.hour

    daily_counts    = df.groupby("date").size()
    hourly_counts   = df.groupby("hour").size()
    plate_counts    = df["license_plate"].value_counts()
    etl             = df["etl_status"].value_counts()

    return {
        "total":              len(df),
        "per_type":           df["violation_type"].value_counts().to_dict(),
        "per_camera":         df["camera_id"].value_counts().to_dict(),
        "per_vehicle":        df["vehicle_type"].value_counts().to_dict(),
        "avg_duration":       round(float(df["duration_seconds"].mean()), 1),
        "max_duration":       round(float(df["duration_seconds"].max()), 1),
        "unique_plates":      int(df["license_plate"].nunique()),
        "etl_issued":         int(etl.get("issued", 0)),
        "etl_pending":        int(etl.get("pending", 0)),
        "etl_paid":           int(etl.get("paid", 0)),
        "busiest_day":        str(daily_counts.idxmax()) if not daily_counts.empty else None,
        "busiest_day_count":  int(daily_counts.max()) if not daily_counts.empty else 0,
        "busiest_hour":       int(hourly_counts.idxmax()) if not hourly_counts.empty else None,
        "top_offender_plate": str(plate_counts.index[0]) if not plate_counts.empty else None,
        "top_offender_count": int(plate_counts.iloc[0]) if not plate_counts.empty else 0,
    }


# ============================================================
# RECIDIVISM ANALYSIS
# ============================================================

def get_recidivism_analysis(days_back: int = 30) -> dict:
    """
    Analisis mendalam pelanggar berulang.

    Returns:
        {
          "total_repeat_offenders": int,
          "recidivism_rate": float,       # % kendaraan yang melanggar >1x
          "high_risk_count": int,
          "offenders_df": DataFrame,
          "avg_violations_per_offender": float,
        }
    """
    df       = get_violations_df(days_back=days_back)
    offenders = get_repeat_offenders(days_back=days_back, min_count=2)

    if df.empty:
        return {
            "total_repeat_offenders": 0,
            "recidivism_rate": 0.0,
            "high_risk_count": 0,
            "offenders_df": pd.DataFrame(),
            "avg_violations_per_offender": 0.0,
        }

    unique_plates = df["license_plate"].nunique()
    repeat_count  = len(offenders)

    high_risk = offenders[offenders["risk_level"] == "🔴 Tinggi"] if not offenders.empty else pd.DataFrame()

    return {
        "total_repeat_offenders":      repeat_count,
        "recidivism_rate":             round(repeat_count / unique_plates * 100, 1) if unique_plates else 0,
        "high_risk_count":             len(high_risk),
        "offenders_df":                offenders,
        "avg_violations_per_offender": round(float(offenders["count"].mean()), 1) if not offenders.empty else 0.0,
    }


# ============================================================
# HOURLY HEATMAP DATA
# ============================================================

def get_hourly_heatmap(days_back: int = 30) -> pd.DataFrame:
    """
    Matrix jam × hari untuk heatmap visualisasi.

    Returns:
        DataFrame index=day_name, columns=0..23, values=count
    """
    df = get_violations_df(days_back=days_back)
    if df.empty:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"]      = df["timestamp"].dt.hour
    df["day_name"]  = df["timestamp"].dt.day_name()

    pivot = df.pivot_table(
        index="day_name", columns="hour",
        values="id", aggfunc="count", fill_value=0
    )

    day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])

    # Pastikan semua jam 0-23 ada
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]

    return pivot


# ============================================================
# ZONE ANALYSIS
# ============================================================

def get_zone_analysis(days_back: int = 30) -> pd.DataFrame:
    """
    Analisis pelanggaran per zona deteksi.

    Returns:
        DataFrame: zone_name, count, avg_duration, violation_type
    """
    df = get_violations_df(days_back=days_back)
    if df.empty or "zone_name" not in df.columns:
        return pd.DataFrame()

    zone_stats = (
        df.groupby(["zone_name", "violation_type"])
        .agg(
            count=("id", "count"),
            avg_duration=("duration_seconds", "mean"),
        )
        .reset_index()
        .sort_values("count", ascending=False)
    )
    zone_stats["avg_duration"] = zone_stats["avg_duration"].round(1)
    return zone_stats


# ============================================================
# ENFORCEMENT RATE
# ============================================================

def get_enforcement_rate(days_back: int = 30) -> dict:
    """
    Hitung enforcement rate (% pelanggaran yang sudah di-ETL).

    Returns:
        {"rate": float, "issued": int, "total": int}
    """
    df = get_violations_df(days_back=days_back)
    if df.empty:
        return {"rate": 0.0, "issued": 0, "total": 0}

    total  = len(df)
    issued = int((df["etl_status"] != "pending").sum())
    rate   = round(issued / total * 100, 1) if total else 0.0

    return {"rate": rate, "issued": issued, "total": total}


# ============================================================
# STANDALONE — VERIFIKASI
# ============================================================

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)

    print("🔍 Menjalankan semua fungsi analytics...\n")

    # Peak hours
    peak = get_peak_violation_hours()
    print(f"⏰ Peak hour    : {peak['peak_hour']:02d}:00")
    print(f"   Top 3 hours  : {[f'{h:02d}:00' for h in peak['peak_hours']]}")

    # Hotspots
    hotspots = get_camera_hotspots()
    if hotspots:
        top = hotspots[0]
        print(f"\n📍 Hotspot teratas: {top['name']} ({top['count']} pelanggaran, {top['percentage']}%)")

    # Summary
    summary = get_violation_summary()
    print(f"\n📊 Summary:")
    print(f"   Total          : {summary['total']:,}")
    print(f"   Unique plates  : {summary['unique_plates']:,}")
    print(f"   Busiest day    : {summary['busiest_day']} ({summary['busiest_day_count']} violations)")
    print(f"   Busiest hour   : {summary['busiest_hour']:02d}:00" if summary['busiest_hour'] is not None else "   Busiest hour   : -")
    print(f"   Avg duration   : {summary['avg_duration']}s")

    # Recidivism
    recid = get_recidivism_analysis()
    print(f"\n🔁 Recidivism:")
    print(f"   Repeat offenders : {recid['total_repeat_offenders']}")
    print(f"   Rate             : {recid['recidivism_rate']}%")
    print(f"   High risk        : {recid['high_risk_count']}")

    # Enforcement rate
    enf = get_enforcement_rate()
    print(f"\n🎫 Enforcement rate: {enf['rate']}% ({enf['issued']}/{enf['total']})")

    # Heatmap shape
    hm = get_hourly_heatmap()
    if not hm.empty:
        print(f"\n🗓️  Heatmap matrix  : {hm.shape[0]} hari × {hm.shape[1]} jam")

    print("\n✅ Semua fungsi analytics berjalan dengan baik!")
