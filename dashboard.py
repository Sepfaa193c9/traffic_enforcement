# ============================================================
# dashboard.py — Streamlit Dashboard (7 Halaman)
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================

import time
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import sqlite3
import os
import sys

# Tambahkan direktori saat ini ke path
sys.path.insert(0, os.path.dirname(__file__))

from config import (
    DB_PATH, CAMERA_LOCATIONS, DASHBOARD_TITLE,
    VIOLATION_TYPES, YOLO_MODEL, ACTIVE_CAMERA_ID
)
from database import (
    get_violations_df, get_statistics,
    generate_etl_ticket, get_repeat_offenders,
    DatabaseManager
)

# ============================================================
# AUTO-GENERATE DATABASE JIKA TIDAK ADA
# ============================================================
@st.cache_resource

def _init_database():
    """Initialize database with sample data if not exists"""
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 5000:
        try:
            print("[*] Database kosong, insert sample data...")
            from generate_demo_data import generate_demo_data
            generate_demo_data(count=300, days_back=30)
            print("[✓] Sample data inserted")
            return True
        except Exception as e:
            print(f"[!] Error insert sample data: {e}")
            return False
    return True

# Init database on startup
_init_database()
# DEBUG — hapus setelah fix
_init_database()
st.write("DB exists:", os.path.exists(DB_PATH))
st.write("DB path:", DB_PATH)
try:
    df_test = get_violations_df(days_back=30)
    st.write("Row count:", len(df_test))
except Exception as e:
    st.write("ERROR:", e)
# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="DISHUB DKI - Traffic Enforcement",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# CUSTOM CSS
# ============================================================
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        color: white;
        margin-bottom: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .metric-card h2 { font-size: 2.2em; margin: 0; font-weight: 700; }
    .metric-card p  { margin: 4px 0 0; opacity: 0.85; font-size: 0.9em; }

    .violation-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.8em;
        font-weight: 600;
    }
    .badge-busway   { background: #ff4b4b22; color: #ff4b4b; }
    .badge-parking  { background: #ffa50022; color: #ffa500; }
    .badge-bike     { background: #00c85322; color: #00c853; }
    .badge-wrong    { background: #9c27b022; color: #9c27b0; }

    /* NAVBAR HORIZONTAL */
    .navbar-container {
        background: linear-gradient(90deg, #1e3a5f 0%, #2d6a9f 100%);
        width: 100%;
        box-sizing: border-box;
        border-radius: 12px;
        padding: 15px 0;
        margin-bottom: 25px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.15);
    }

    .navbar-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 2px solid rgba(255,255,255,0.2);
    }

    .navbar-title {
        font-size: 1.5em;
        font-weight: 700;
        color: white;
        margin: 0;
    }

    .navbar-subtitle {
        font-size: 0.85em;
        color: rgba(255,255,255,0.8);
        margin: 0;
    }

    .navbar-nav {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        align-items: center;
    }

    .nav-button {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.9em;
        text-align: center;
        cursor: pointer;
        transition: all 0.3s ease;
        border: 2px solid rgba(255,255,255,0.3);
        color: white;
        background: rgba(255,255,255,0.1);
        text-decoration: none;
    }

    .nav-button:hover {
        background: rgba(255,255,255,0.2);
        border-color: rgba(255,255,255,0.6);
    }

    .nav-button.active {
        background: rgba(255,255,255,0.3);
        border-color: white;
        box-shadow: 0 0 10px rgba(255,255,255,0.3);
    }

    .navbar-right {
        display: flex;
        gap: 15px;
        align-items: center;
    }

    div[data-testid="stMetricValue"] { font-size: 2em !important; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HELPERS
# ============================================================

VIOLATION_LABELS = {
    "busway_violation":    "Jalur Bus",
    "bike_lane_violation": "Jalur Sepeda",
    "illegal_parking":     "Parkir Illegal",
    "wrong_way":           "Lawan Arah",
}

VEHICLE_LABELS = {
    "car":        "Mobil",
    "motorcycle": "Motor",
    "bus":        "Bus",
    "truck":      "Truk",
    "bicycle":    "Sepeda",
}

COLOR_MAP = {
    "busway_violation":    "#ff4b4b",
    "bike_lane_violation": "#00c853",
    "illegal_parking":     "#ffa500",
    "wrong_way":           "#9c27b0",
}

@st.cache_data(ttl=30)
def load_data(days_back: int = 30) -> pd.DataFrame:
    df = get_violations_df(days_back=days_back)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["hour"]      = df["timestamp"].dt.hour
        df["day_name"]  = df["timestamp"].dt.day_name()
        df["date"]      = df["timestamp"].dt.date
        df["vtype_label"]   = df["violation_type"].map(VIOLATION_LABELS).fillna(df["violation_type"])
        df["vehicle_label"] = df["vehicle_type"].map(VEHICLE_LABELS).fillna(df["vehicle_type"])
    return df

@st.cache_data(ttl=30)
def load_stats(days_back: int = 30) -> dict:
    return get_statistics(days_back=days_back)

def empty_state(msg: str = "Belum ada data. Jalankan `generate_demo_data.py` terlebih dahulu."):
    st.info(f"{msg}")

# ============================================================
# NAVBAR HORIZONTAL
# ============================================================

def render_navbar() -> tuple[str, int]:
    """Render horizontal navbar with navigation and controls"""
    
    col_header, col_right = st.columns([1, 0.3])
    
    with col_header:
        st.markdown("""
        <div class="navbar-container">
            <div class="navbar-header">
                <div>
                    <p class="navbar-title">DISHUB DKI Jakarta</p>
                    <p class="navbar-subtitle">Traffic Enforcement System</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Navigation items
    nav_items = [
        "Dashboard",
        "Analytics",
        "E-TLE Integration",
        "Reports",
        "Heatmap",
        "Real-time Monitor",
        "Settings",
    ]
    
    # Store page state in session
    if "current_page" not in st.session_state:
        st.session_state.current_page = nav_items[0]
    
    # Navigation buttons
    st.markdown("<div class='navbar-nav'>", unsafe_allow_html=True)
    nav_cols = st.columns(len(nav_items))
    
    for idx, (col, item) in enumerate(zip(nav_cols, nav_items)):
        with col:
            if st.button(item, use_container_width=True, 
                        key=f"nav_{idx}"):
                st.session_state.current_page = item
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Controls section (di bawah navbar)
    st.markdown("---")
    col_period, col_refresh = st.columns([1, 0.5])
    
    with col_period:
        days_back = st.select_slider(
            "Periode Data",
            options=[1, 3, 7, 14, 30, 60, 90],
            value=30,
            format_func=lambda x: f"{x} hari",
            label_visibility="collapsed",
        )
    
    with col_refresh:
        if st.button("Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    st.markdown("---")
    
    # Extract page name (remove emoji)
    page_name = st.session_state.current_page.split(" ", 1)[1] if " " in st.session_state.current_page else st.session_state.current_page
    
    return page_name, days_back

# ============================================================
# PAGE 1 — DASHBOARD
# ============================================================

def page_dashboard(df: pd.DataFrame, stats: dict):
    st.title("Dashboard Utama")
    st.caption(f"Sistem deteksi pelanggaran lalu lintas otomatis - {datetime.now().strftime('%d %B %Y')}")

    if df.empty:
        empty_state()
        return

    # --- Metric Cards ---
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Pelanggaran", f"{stats['total']:,}")
    with col2:
        busway = stats["per_type"].get("busway_violation", 0)
        st.metric("Jalur Bus", f"{busway:,}")
    with col3:
        parking = stats["per_type"].get("illegal_parking", 0)
        st.metric("Parkir Illegal", f"{parking:,}")
    with col4:
        st.metric("Plat Unik", f"{stats['unique_plates']:,}")
    with col5:
        st.metric("Rata-rata Durasi", f"{stats['avg_duration']:.0f}s")

    st.markdown("---")

    col_left, col_right = st.columns([1, 1])

    # Pie chart - violation types
    with col_left:
        st.subheader("Distribusi Jenis Pelanggaran")
        vtype_counts = df["vtype_label"].value_counts().reset_index()
        vtype_counts.columns = ["Jenis", "Jumlah"]
        fig_pie = px.pie(
            vtype_counts, values="Jumlah", names="Jenis",
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.4,
        )
        fig_pie.update_traces(textposition="outside", textinfo="percent+label")
        fig_pie.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    # Bar chart - per camera
    with col_right:
        st.subheader("Pelanggaran per Kamera")
        cam_data = df["camera_id"].value_counts().reset_index()
        cam_data.columns = ["Kamera", "Jumlah"]
        cam_data["Lokasi"] = cam_data["Kamera"].map(
            {k: v["name"] for k, v in CAMERA_LOCATIONS.items()}
        ).fillna(cam_data["Kamera"])
        fig_bar = px.bar(
            cam_data, x="Lokasi", y="Jumlah",
            color="Jumlah", color_continuous_scale="Blues",
            text="Jumlah",
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(
            coloraxis_showscale=False,
            margin=dict(t=10, b=10),
            xaxis_title="", yaxis_title="Jumlah Pelanggaran",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # Hourly trend line
    st.subheader("Tren Pelanggaran per Jam")
    hourly = df.groupby(["hour", "vtype_label"]).size().reset_index(name="count")
    fig_line = px.line(
        hourly, x="hour", y="count", color="vtype_label",
        markers=True,
        labels={"hour": "Jam", "count": "Jumlah", "vtype_label": "Jenis"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_line.update_layout(xaxis=dict(tickmode="linear", dtick=1), margin=dict(t=10))
    st.plotly_chart(fig_line, use_container_width=True)

    # Recent violations table
    st.subheader("Pelanggaran Terbaru")
    recent = df.head(15)[["timestamp", "camera_id", "vehicle_label", "license_plate",
                           "vtype_label", "duration_seconds", "etl_status"]].copy()
    recent.columns = ["Waktu", "Kamera", "Kendaraan", "Plat", "Pelanggaran", "Durasi (s)", "Status E-TLE"]
    recent["Waktu"] = recent["Waktu"].dt.strftime("%d/%m %H:%M:%S")
    st.dataframe(recent, use_container_width=True, hide_index=True)

# ============================================================
# PAGE 2 — ANALYTICS
# ============================================================

def page_analytics(df: pd.DataFrame, days_back: int):
    st.title("Analytics Mendalam")

    if df.empty:
        empty_state()
        return

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Pola Waktu", "Kendaraan", "Per Lokasi", "Recidivism"]
    )

    with tab1:
        st.subheader("Heatmap Jam x Hari")
        days_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        pivot = df.pivot_table(index="day_name", columns="hour", values="id",
                               aggfunc="count", fill_value=0)
        pivot = pivot.reindex([d for d in days_order if d in pivot.index])
        fig_hm = px.imshow(
            pivot, aspect="auto",
            color_continuous_scale="YlOrRd",
            labels={"x": "Jam", "y": "Hari", "color": "Jumlah"},
        )
        fig_hm.update_layout(margin=dict(t=20))
        st.plotly_chart(fig_hm, use_container_width=True)

        st.subheader("Distribusi Jam Peak")
        peak = df.groupby("hour").size().reset_index(name="count")
        fig_peak = px.bar(peak, x="hour", y="count", color="count",
                          color_continuous_scale="Reds",
                          labels={"hour": "Jam", "count": "Jumlah"})
        fig_peak.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_peak, use_container_width=True)

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribusi Jenis Kendaraan")
            veh = df["vehicle_label"].value_counts().reset_index()
            veh.columns = ["Kendaraan", "Jumlah"]
            fig_v = px.bar(veh, x="Kendaraan", y="Jumlah",
                           color="Jumlah", color_continuous_scale="Teal",
                           text="Jumlah")
            fig_v.update_traces(textposition="outside")
            fig_v.update_layout(coloraxis_showscale=False, xaxis_title="")
            st.plotly_chart(fig_v, use_container_width=True)

        with col2:
            st.subheader("Kendaraan vs Jenis Pelanggaran")
            cross = df.groupby(["vehicle_label", "vtype_label"]).size().reset_index(name="count")
            fig_cross = px.bar(cross, x="vehicle_label", y="count",
                               color="vtype_label", barmode="stack",
                               labels={"vehicle_label": "Kendaraan",
                                       "count": "Jumlah", "vtype_label": "Jenis"},
                               color_discrete_sequence=px.colors.qualitative.Set2)
            fig_cross.update_layout(xaxis_title="", legend_title="Jenis Pelanggaran")
            st.plotly_chart(fig_cross, use_container_width=True)

        st.subheader("Durasi Parkir Illegal")
        parking_df = df[df["violation_type"] == "illegal_parking"]
        if not parking_df.empty:
            fig_dur = px.histogram(parking_df, x="duration_seconds",
                                   nbins=30, color_discrete_sequence=["#ffa500"],
                                   labels={"duration_seconds": "Durasi (detik)"})
            st.plotly_chart(fig_dur, use_container_width=True)
        else:
            st.info("Tidak ada data parkir Illegal dalam periode ini.")

    with tab3:
        st.subheader("Tren Harian per Kamera")
        daily_cam = df.groupby(["date", "camera_id"]).size().reset_index(name="count")
        daily_cam["Lokasi"] = daily_cam["camera_id"].map(
            {k: v["name"] for k, v in CAMERA_LOCATIONS.items()}
        ).fillna(daily_cam["camera_id"])
        fig_cam = px.line(daily_cam, x="date", y="count", color="Lokasi",
                          markers=True,
                          labels={"date": "Tanggal", "count": "Jumlah"})
        st.plotly_chart(fig_cam, use_container_width=True)

        st.subheader("Ranking Kamera Total Pelanggaran")
        cam_rank = df["camera_id"].value_counts().reset_index()
        cam_rank.columns = ["camera_id", "Total"]
        cam_rank["Lokasi"] = cam_rank["camera_id"].map(
            {k: v["name"] for k, v in CAMERA_LOCATIONS.items()}
        ).fillna(cam_rank["camera_id"])
        fig_rank = px.bar(cam_rank.sort_values("Total"), x="Total", y="Lokasi",
                          orientation="h", text="Total",
                          color="Total", color_continuous_scale="Blues")
        fig_rank.update_traces(textposition="outside")
        fig_rank.update_layout(coloraxis_showscale=False, yaxis_title="")
        st.plotly_chart(fig_rank, use_container_width=True)

    with tab4:
        st.subheader("Analisis Pelanggar Berulang")
        offenders = get_repeat_offenders(days_back=days_back, min_count=2)
        if offenders.empty:
            st.info("Belum ada pelanggar berulang dalam periode ini.")
        else:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Pelanggar Berulang", len(offenders))
            col2.metric("Pelanggaran Tertinggi", int(offenders["count"].max()))
            col3.metric("Rata-rata Pelanggaran", f"{offenders['count'].mean():.1f}")

            fig_off = px.bar(
                offenders.head(15),
                x="license_plate", y="count",
                color="risk_level",
                color_discrete_map={"Tinggi": "#ff4b4b", "Sedang": "#ffa500", "Rendah": "#ffd700"},
                text="count",
                labels={"license_plate": "Plat Nomor", "count": "Jumlah Pelanggaran"},
            )
            fig_off.update_traces(textposition="outside")
            fig_off.update_layout(xaxis_title="", legend_title="Risk Level")
            st.plotly_chart(fig_off, use_container_width=True)

            st.dataframe(offenders[["license_plate", "count", "risk_level",
                                    "last_violation", "violation_types"]],
                         use_container_width=True, hide_index=True)

# ============================================================
# PAGE 3 — E-TLE INTEGRATION
# ============================================================

def page_etle(df: pd.DataFrame):
    st.title("E-TLE Integration")
    st.caption("Electronic Traffic Law Enforcement - penerbitan tiket digital")

    if df.empty:
        empty_state()
        return

    col1, col2, col3 = st.columns(3)
    etl = df["etl_status"].value_counts()
    col1.metric("Pending",  int(etl.get("pending", 0)))
    col2.metric("Issued",   int(etl.get("issued",  0)))
    col3.metric("Paid",     int(etl.get("paid",    0)))

    st.markdown("---")

    # Filter
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox("Filter Status", ["Semua", "pending", "issued", "paid"])
    with col_f2:
        plate_search = st.text_input("Cari Plat Nomor", placeholder="contoh: B1234XX")

    filtered = df.copy()
    if status_filter != "Semua":
        filtered = filtered[filtered["etl_status"] == status_filter]
    if plate_search:
        filtered = filtered[filtered["license_plate"].str.contains(plate_search.upper(), na=False)]

    display = filtered[["id", "timestamp", "license_plate", "vtype_label",
                         "vehicle_label", "camera_id", "etl_status", "etl_ticket_id"]].head(100)
    display.columns = ["ID", "Waktu", "Plat", "Pelanggaran", "Kendaraan", "Kamera", "Status", "Tiket ID"]
    display["Waktu"] = display["Waktu"].dt.strftime("%d/%m/%Y %H:%M")

    st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Terbitkan Tiket E-TLE")

    col_a, col_b = st.columns([1, 2])
    with col_a:
        viol_id = st.number_input("ID Pelanggaran", min_value=1, step=1)
        if st.button("Generate Tiket", type="primary", use_container_width=True):
            ticket = generate_etl_ticket(int(viol_id))
            if ticket:
                st.success(f"Tiket diterbitkan: **{ticket}**")
                st.cache_data.clear()
            else:
                st.error("Gagal menerbitkan tiket. Pastikan ID valid.")

    with col_b:
        pending_ids = df[df["etl_status"] == "pending"]["id"].tolist()
        if pending_ids and st.button(f"Terbitkan Semua Pending ({len(pending_ids)} tiket)",
                                     use_container_width=True):
            progress = st.progress(0)
            issued = 0
            for i, vid in enumerate(pending_ids[:50]):  # max 50 sekaligus
                if generate_etl_ticket(vid):
                    issued += 1
                progress.progress((i + 1) / min(len(pending_ids), 50))
            st.success(f"{issued} tiket berhasil diterbitkan!")
            st.cache_data.clear()

# ============================================================
# PAGE 4 — REPORTS
# ============================================================

def page_reports(df: pd.DataFrame, days_back: int):
    st.title("Generator Laporan")

    st.markdown("""
    Generate laporan Excel multi-sheet resmi untuk:
    - Laporan harian / mingguan / bulanan
    - Export data mentah pelanggaran
    - Analisis recidivism
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        report_days = st.selectbox("Periode Laporan", [7, 14, 30, 60, 90],
                                   index=2, format_func=lambda x: f"{x} hari")
    with col2:
        cam_filter = st.selectbox("Filter Kamera",
                                  ["Semua"] + [f"{k} - {v['name']}"
                                               for k, v in CAMERA_LOCATIONS.items()])
    with col3:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        generate_btn = st.button("Generate Laporan Excel", type="primary",
                                 use_container_width=True)

    if generate_btn:
        try:
            import subprocess
            cam_arg = cam_filter.split(" - ")[0] if cam_filter != "Semua" else ""
            cmd = ["python", "report_generator.py", "--days", str(report_days)]
            with st.spinner("Membuat laporan..."):
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                # Cari file terbaru
                xlsx_files = sorted(
                    [f for f in os.listdir(".") if f.startswith("Laporan_DISHUB") and f.endswith(".xlsx")],
                    reverse=True
                )
                if xlsx_files:
                    with open(xlsx_files[0], "rb") as f:
                        st.download_button(
                            f"Download {xlsx_files[0]}",
                            data=f.read(),
                            file_name=xlsx_files[0],
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    st.success(f"Laporan siap: `{xlsx_files[0]}`")
                else:
                    st.warning("Laporan dibuat tapi file tidak ditemukan. Cek folder proyek.")
            else:
                st.error(f"Error saat generate: {result.stderr}")
                st.info("Pastikan `report_generator.py` sudah ada di folder proyek.")
        except FileNotFoundError:
            st.error("`report_generator.py` tidak ditemukan.")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("Export Data Mentah (CSV)")

    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        fname = f"violations_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        st.download_button("Download CSV", data=csv, file_name=fname, mime="text/csv")
        st.caption(f"{len(df):,} baris data siap diexport")
    else:
        empty_state()

# ============================================================
# PAGE 5 — HEATMAP
# ============================================================

def page_heatmap(df: pd.DataFrame):
    st.title("Heatmap Pelanggaran")

    # Buat peta Folium berpusat di Jakarta
    m = folium.Map(location=[-6.2088, 106.8456], zoom_start=12,
                   tiles="CartoDB positron")

    # Tambahkan marker per kamera
    cameras = DatabaseManager().get_cameras()
    for cam in cameras:
        if not cam.get("latitude"):
            continue

        cam_id   = cam["camera_id"]
        cam_name = cam.get("name", cam_id)

        # Hitung pelanggaran di kamera ini
        count = len(df[df["camera_id"] == cam_id]) if not df.empty else 0

        # Warna marker berdasarkan jumlah
        color = "red" if count > 50 else "orange" if count > 20 else "green"

        popup_html = f"""
        <b>{cam_name}</b><br>
        {cam_id}<br>
        Pelanggaran: <b>{count}</b><br>
        """
        if not df.empty:
            types = df[df["camera_id"] == cam_id]["violation_type"].value_counts()
            for vt, cnt in types.items():
                popup_html += f"• {VIOLATION_LABELS.get(vt, vt)}: {cnt}<br>"

        folium.Marker(
            location=[cam["latitude"], cam["longitude"]],
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=f"{cam_name} ({count} pelanggaran)",
            icon=folium.Icon(color=color, icon="camera", prefix="fa"),
        ).add_to(m)

    # Heat layer jika ada data dengan koordinat
    if not df.empty and "latitude" in df.columns:
        heat_df = df.dropna(subset=["latitude", "longitude"])
        if not heat_df.empty:
            from folium.plugins import HeatMap
            heat_data = heat_df[["latitude", "longitude"]].values.tolist()
            HeatMap(heat_data, radius=25, blur=15, min_opacity=0.3).add_to(m)

    col1, col2 = st.columns([3, 1])
    with col1:
        st_folium(m, width="100%", height=500)

    with col2:
        st.subheader("Legenda")
        st.markdown("**Merah** - > 50 pelanggaran")
        st.markdown("**Oranye** - > 20 pelanggaran")
        st.markdown("**Hijau** - <= 20 pelanggaran")
        st.markdown("---")
        st.subheader("Hotspot")
        if not df.empty:
            top_cams = df["camera_id"].value_counts().head(5).reset_index()
            top_cams.columns = ["cam_id", "count"]
            top_cams["nama"] = top_cams["cam_id"].map(
                {k: v["name"] for k, v in CAMERA_LOCATIONS.items()}
            ).fillna(top_cams["cam_id"])
            for _, row in top_cams.iterrows():
                st.markdown(f"**{row['nama']}** - {row['count']} pelanggaran")

# ============================================================
# PAGE 6 — REAL-TIME MONITOR
# ============================================================

def page_realtime():
    st.title("📱 Real-time Monitor")

    url = st.text_input(
        "Stream URL",
        placeholder="https://www.youtube.com/watch?v=... atau URL HLS .m3u8",
    )

    col1, col2 = st.columns(2)
    with col1:
        interval = st.selectbox("Refresh tiap", [1, 2, 3, 5], index=1,
                                format_func=lambda x: f"{x} detik")
    with col2:
        conf = st.slider("Confidence", 0.1, 0.9, 0.35)

    run = st.toggle("▶ Mulai Stream")

    frame_placeholder = st.empty()
    stats_placeholder = st.empty()

    if not run or not url:
        frame_placeholder.info("Masukkan URL dan aktifkan stream.")
        return

    # Resolve YouTube URL → direct stream
    import subprocess, shutil
    stream_url = url
    if "youtube.com" in url or "youtu.be" in url:
        if not shutil.which("yt-dlp"):
            st.error("yt-dlp tidak tersedia di server.")
            return
        with st.spinner("Mengambil stream URL..."):
            res = subprocess.run(
                ["yt-dlp", "-g", "-f", "best[height<=480]/best",
                 "--no-warnings", "--no-playlist", url],
                capture_output=True, text=True, timeout=30
            )
        if res.returncode != 0:
            st.error(f"Gagal resolve URL: {res.stderr.strip()}")
            return
        urls = [u.strip() for u in res.stdout.strip().splitlines() if u.strip()]
        if not urls:
            st.error("Tidak ada stream yang didapat.")
            return
        stream_url = urls[0]
        st.success("Stream URL didapat!")

    # Load model (cache agar tidak reload tiap frame)
    @st.cache_resource
    def load_model():
        from ultralytics import YOLO
        return YOLO("yolov8n.pt")

    model = load_model()

    # Baca 1 frame via ffmpeg pipe
    def grab_frame(src_url):
        if not shutil.which("ffmpeg"):
            return None
        cmd = [
            "ffmpeg", "-loglevel", "error",
            "-i", src_url,
            "-frames:v", "1",       # ambil 1 frame saja
            "-f", "image2pipe",
            "-pix_fmt", "bgr24",
            "-vcodec", "rawvideo", "-",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=10)
            raw = proc.stdout
            if not raw:
                return None
            import numpy as np
            # Decode ukuran dari panjang raw (480p = 640x480x3)
            n = len(raw)
            # Coba beberapa resolusi umum
            for w, h in [(640,480),(854,480),(1280,720),(1920,1080)]:
                if n == w * h * 3:
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 3))
                    return frame
            # Fallback: decode via Pillow
            from PIL import Image
            import io
            proc2 = subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-i", src_url,
                 "-frames:v", "1", "-f", "mjpeg", "-"],
                capture_output=True, timeout=10
            )
            img = Image.open(io.BytesIO(proc2.stdout))
            import numpy as np
            return np.array(img)[:, :, ::-1]
        except Exception as e:
            st.warning(f"Frame error: {e}")
            return None

    # Loop display
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=interval * 1000, key="realtime_refresh")

    with st.spinner("Mengambil frame..."):
        frame = grab_frame(stream_url)

    if frame is None:
        frame_placeholder.warning("Gagal ambil frame. Stream mungkin tidak tersedia.")
        return

    # Inferensi YOLO
    import cv2
    results = model(frame, conf=conf, verbose=False)[0]
    annotated = results.plot()
    annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)

    frame_placeholder.image(annotated_rgb, channels="RGB", use_container_width=True)

    # Statistik singkat
    n_detected = len(results.boxes)
    classes = [model.names[int(c)] for c in results.boxes.cls]
    from collections import Counter
    counts = Counter(classes)
    stats_placeholder.markdown(
        f"**Terdeteksi:** {n_detected} objek — " +
        " | ".join(f"{v}x {k}" for k, v in counts.items())
                    )

# ============================================================
# PAGE 7 — SETTINGS
# ============================================================

def page_settings():
    st.title("Settings & Informasi Sistem")

    tab1, tab2, tab3 = st.tabs(["Konfigurasi", "Database Info", "System Info"])

    with tab1:
        st.subheader("Konfigurasi Aktif")
        st.json({
            "VIDEO_SOURCE": str(0),
            "YOLO_MODEL": YOLO_MODEL,
            "ACTIVE_CAMERA_ID": ACTIVE_CAMERA_ID,
            "CAMERA_LOCATIONS": {k: v["name"] for k, v in CAMERA_LOCATIONS.items()},
            "VIOLATION_TYPES": VIOLATION_TYPES,
        })
        st.info("Edit `config.py` untuk mengubah konfigurasi sistem.")

    with tab2:
        st.subheader("Statistik Database")
        if os.path.exists(DB_PATH):
            size_mb = os.path.getsize(DB_PATH) / 1024 / 1024
            st.metric("Ukuran Database", f"{size_mb:.2f} MB")

            conn = sqlite3.connect(DB_PATH)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            st.markdown(f"**Tabel:** {', '.join([t[0] for t in tables])}")

            for tname in [t[0] for t in tables]:
                count = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
                st.markdown(f"- `{tname}`: **{count:,}** baris")
            conn.close()

            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Hapus Data Lama (> 1 tahun)", use_container_width=True):
                    DatabaseManager().purge_old_records(365)
                    st.success("Data lama dihapus.")
                    st.cache_data.clear()
            with col_b:
                if st.button("Reset Semua Data", type="secondary", use_container_width=True):
                    st.warning("Yakin? Ini akan menghapus SEMUA data!")
                    if st.button("Konfirmasi Reset"):
                        os.remove(DB_PATH)
                        DatabaseManager()
                        st.success("Database di-reset.")
                        st.cache_data.clear()
        else:
            st.warning("Database belum ditemukan. Jalankan `python database.py` terlebih dahulu.")

    with tab3:
        st.subheader("Tech Stack")
        tech_data = {
            "Komponen": ["Object Detection", "Tracking", "ANPR", "Database", "Dashboard", "Maps", "Charts", "Reports"],
            "Technology": ["YOLOv8 (Ultralytics)", "ByteTrack (Supervision)", "EasyOCR", "SQLite", "Streamlit", "Folium", "Plotly", "OpenPyXL"],
            "Status": ["Free"] * 8,
        }
        st.dataframe(pd.DataFrame(tech_data), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("**Version:** 1.1.0 | **Last Updated:** May 2026")
        st.markdown("**Built for:** AI Open Innovation Challenge 2026 - DISHUB DKI Jakarta")

# ============================================================
# MAIN
# ============================================================

def main():
    page, days_back = render_navbar()

    df    = load_data(days_back)
    stats = load_stats(days_back)

    if   page == "Dashboard":         page_dashboard(df, stats)
    elif page == "Analytics":         page_analytics(df, days_back)
    elif page == "E-TLE Integration": page_etle(df)
    elif page == "Reports":           page_reports(df, days_back)
    elif page == "Heatmap":           page_heatmap(df)
    elif page == "Real-time Monitor": page_realtime()
    elif page == "Settings":          page_settings()

if __name__ == "__main__":
    main()
