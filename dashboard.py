# ============================================================
# dashboard.py — Streamlit Dashboard (7 Halaman) - FIXED PRODUCTION
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
sys.path.insert(0, os.path.dirname(__file__)))

from config import (
    DB_PATH, CAMERA_LOCATIONS, DASHBOARD_TITLE,
    VIOLATION_TYPES, YOLO_MODEL, ACTIVE_CAMERA_ID
)
from database import (
    get_violations_df, get_statistics,
    generate_etl_ticket, get_repeat_offenders,
    DatabaseManager
)

# Set Page Config (Harus di bagian paling atas script utama)
st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS untuk tampilan premium khas DKI Jakarta
st.markdown("""
<style>
    .reportview-container { background: #f0f2f6; }
    .metric-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border-left: 5px solid #003366;
        margin-bottom: 15px;
    }
    .stButton>button {
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

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
            print(f"[!] Gagal membuat data simulasi: {e}")
    return False

_init_database()

# ============================================================
# DATA LOADERS WITH CACHE
# ============================================================
@st.cache_data(ttl=5)
def load_data(days_back=7):
    return get_violations_df(days_back=days_back)

@st.cache_data(ttl=5)
def load_stats(days_back=7):
    return get_statistics(days_back=days_back)

# ============================================================
# NAVIGATION BAR
# ============================================================
def render_navbar():
    st.sidebar.image(
        "https://upload.wikimedia.org/wikipedia/commons/b/b4/Logo_Dishub_DKI_Jakarta.png",
        width=90
    )
    st.sidebar.title("🚨 DISHUB DKI Jakarta")
    st.sidebar.subheader("Traffic Enforcement AI")
    st.sidebar.markdown("---")
    
    page = st.sidebar.radio(
        "Menu Navigasi",
        [
            "Dashboard", 
            "Analytics", 
            "E-TLE Integration", 
            "Reports", 
            "Heatmap", 
            "Real-time Monitor", 
            "Settings"
        ]
    )
    
    st.sidebar.markdown("---")
    days_back = st.sidebar.slider("Rentang Data (Hari Terakhir)", 1, 90, 7)
    
    st.sidebar.markdown("---")
    st.sidebar.info(
        "📊 **Sistem Aktif**\n"
        "Engine: YOLOv8 + EasyOCR\n"
        "Status Platform: Operational"
    )
    
    return page, days_back

# ============================================================
# HALAMAN 1: DASHBOARD UTAMA
# ============================================================
def page_dashboard(df, stats):
    st.title("📊 Eksekutif Dashboard Pelanggaran Lalu Lintas")
    st.markdown(f"Analisis real-time menggunakan computer vision pada koridor jalan DKI Jakarta.")
    
    if df.empty:
        st.warning("Tidak ada data pelanggaran pada rentang waktu ini.")
        return

    # Row 1: Metrics Cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><h5>Total Pelanggaran</h5><h2>{stats["total_violations"]:,}</h2><p style="color:gray;font-size:0.8em;">kasus terekam</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card" style="border-left-color:#ffcc00;"><h5>Pelanggaran Hari Ini</h5><h2>{stats["today_violations"]:,}</h2><p style="color:gray;font-size:0.8em;">live update</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card" style="border-left-color:#cc0000;"><h5>Akurasi Rata-rata AI</h5><h2>{stats["avg_confidence"]*100:.1f}%</h2><p style="color:gray;font-size:0.8em;">YOLOv8 Object Detection</p></div>', unsafe_allow_html=True)
    with c4:
        active_cams = df['camera_id'].nunique() if 'camera_id' in df.columns else 0
        st.markdown(f'<div class="metric-card" style="border-left-color:#009933;"><h5>Kamera Aktif</h5><h2>{active_cams}/{len(CAMERA_LOCATIONS)}</h2><p style="color:gray;font-size:0.8em;">titik sensor terintegrasi</p></div>', unsafe_allow_html=True)

    # Row 2: Charts
    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("📈 Tren Pelanggaran Harian")
        if 'timestamp' in df.columns:
            df_trend = df.copy()
            df_trend['date'] = pd.to_datetime(df_trend['timestamp']).dt.date
            trend_data = df_trend.groupby(['date', 'vtype_label']).size().reset_index(name='jumlah')
            fig = px.line(trend_data, x='date', y='jumlah', color='vtype_label', markers=True, template="plotly_white")
            fig.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=350)
            st.plotly_chart(fig, use_container_width=True)
            
    with col2:
        st.subheader("🍕 Distribusi Jenis Pelanggaran")
        v_counts = df['vtype_label'].value_counts().reset_index()
        v_counts.columns = ['Jenis Pelanggaran', 'Jumlah']
        fig_pie = px.pie(v_counts, values='Jumlah', names='Jenis Pelanggaran', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_pie.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=350)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Row 3: Recent Table Log
    st.subheader("📋 Log Pelanggaran Terbaru")
    show_cols = ['timestamp', 'camera_id', 'vtype_label', 'plate_number', 'confidence', 'status']
    existing_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(df[existing_cols].head(10), use_container_width=True)

# ============================================================
# HALAMAN 2: ANALYTICS & TRENDS
# ============================================================
def page_analytics(df, days_back):
    st.title("📈 Analytics & Wawasan Lanjutan")
    if df.empty:
        st.warning("Data kosong.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⏰ Analisis Jam Rawan Pelanggaran")
        df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
        hour_counts = df.groupby('hour').size().reset_index(name='Jumlah')
        fig = px.bar(hour_counts, x='hour', y='Jumlah', labels={'hour':'Jam (WIB)'}, color='Jumlah', color_continuous_scale='Viridis')
        st.plotly_chart(fig, use_container_width=True)
        
    with col2:
        st.subheader("📹 Titik Kamera Paling Banyak Melanggar")
        cam_counts = df['camera_id'].value_counts().reset_index()
        cam_counts.columns = ['Kamera ID', 'Jumlah']
        fig = px.bar(cam_counts, y='Kamera ID', x='Jumlah', orientation='h', color='Jumlah', color_continuous_scale='Reds')
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("🚗 Pelaku Pelanggaran Berulang (Repeat Offenders)")
    offenders = get_repeat_offenders(min_violations=2)
    if not offenders.empty:
        st.dataframe(offenders, use_container_width=True)
    else:
        st.info("Tidak ada kendaraan yang melakukan pelanggaran berulang dalam basis data saat ini.")

# ============================================================
# HALAMAN 3: E-TLE INTEGRATION
# ============================================================
def page_etle(df):
    st.title("✉️ Integrasi Sistem E-TLE Nasional")
    st.markdown("Verifikasi data hasil tangkapan kecerdasan buatan sebelum diteruskan ke Back Office Korlantas POLRI.")

    pending_df = df[df['status'] == 'PENDING'] if 'status' in df.columns else df
    if pending_df.empty:
        st.success("Semua data pelanggaran telah diverifikasi.")
        return

    selected_idx = st.selectbox("Pilih ID Kasus Pelanggaran untuk Diverifikasi:", pending_df.index)
    row = pending_df.loc[selected_idx]

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f"### 📋 Detail Kasus #{row.get('id', selected_idx)}")
        st.write(f"**Waktu Kejadian:** {row.get('timestamp')}")
        st.write(f"**Lokasi Kamera:** {row.get('camera_id')}")
        st.write(f"**Jenis Pelanggaran:** {row.get('vtype_label')}")
        st.write(f"**Skor Deteksi AI:** {row.get('confidence', 0)*100:.1f}%")
        
        # Input manual koreksi jika OCR salah baca
        final_plate = st.text_input("Konfirmasi Nomor Plat Kendaraan:", value=row.get('plate_number', ''))

    with c2:
        st.markdown("### 📸 Bukti Foto Kamera ANPR")
        # Simulasi box placeholder foto kendaraan
        st.info("Kamera ANPR Edge Crop Preview")
        st.image("https://upload.wikimedia.org/wikipedia/commons/a/a1/Indonesian_license_plate_B_1234_EFI.jpg", width=350, caption="Simulasi Capture Plat Nomor")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("✓ Setujui & Kirim Tiket E-TLE", type="primary", use_container_width=True):
            ticket = generate_etl_ticket(int(row.get('id', selected_idx)))
            st.success(f"Sukses! Tiket E-TLE Resmi Diterbitkan dengan Kode Referensi: {ticket['ticket_id']}")
    with col_btn2:
        if st.button("❌ Tolak Kasus (Anomali Objek)", use_container_width=True):
            st.error("Kasus dibatalkan dan status diubah menjadi INVALID.")

# ============================================================
# HALAMAN 4: REPORTS GENERATOR
# ============================================================
def page_reports(df, days_back):
    st.title("📋 Manajemen Laporan & Ekspor")
    st.markdown("Unduh laporan berkala penegakan hukum lalu lintas berbasis AI.")

    st.subheader("Filter Unduhan")
    col1, col2 = st.columns(2)
    with col1:
        v_filter = st.multiselect("Filter Jenis Pelanggaran:", options=df['vtype_label'].unique(), default=df['vtype_label'].unique())
    with col2:
        cam_filter = st.multiselect("Filter Kamera Sensor:", options=df['camera_id'].unique(), default=df['camera_id'].unique())

    filtered_df = df[(df['vtype_label'].isin(v_filter)) & (df['camera_id'].isin(cam_filter))]
    st.dataframe(filtered_df, use_container_width=True)

    # Export Excel Button
    try:
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            filtered_df.to_excel(writer, index=False, sheet_name='Pelanggaran')
        processed_data = output.getvalue()
        
        st.download_button(
            label="📥 Unduh File Excel (.xlsx)",
            data=processed_data,
            file_name=f'laporan_dishub_dki_{datetime.now().strftime("%Y%m%d")}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=True
        )
    except Exception as e:
        st.error(f"Gagal menyiapkan file unduhan: {e}")

# ============================================================
# HALAMAN 5: GEOSPATIAL HEATMAP
# ============================================================
def page_heatmap(df):
    st.title("🗺️ Peta Densitas Titik Rawan Pelanggaran")
    st.markdown("Visualisasi spasial frekuensi penyimpangan marka jalan menggunakan Folium Geomap.")

    # Membuat peta Jakarta Pusat default
    m = folium.Map(location=[-6.1751, 106.8272], zoom_start=12, tiles="OpenStreetMap")
    
    # Hitung jumlah pelanggaran per kamera id
    cam_counts = df['camera_id'].value_counts().to_dict()

    for cam_id, coords in CAMERA_LOCATIONS.items():
        count = cam_counts.get(cam_id, 0)
        # Warna marker dinamis berdasarkan keaktifan kasus
        color = "red" if count > 50 else "orange" if count > 10 else "blue"
        
        folium.CircleMarker(
            location=coords,
            radius=min(25, 5 + (count * 0.2)),
            popup=f"Kamera: {cam_id}<br>Total Kasus Pelanggaran: {count}",
            color=color,
            fill=True,
            fill_opacity=0.6
        ).add_to(m)

    st_folium(m, width="100%", height=500)

# ============================================================
# HALAMAN 6: REAL-TIME MONITOR (FIXED & PENUH)
# ============================================================
def page_realtime():
    st.header("🎥 Real-time Video Monitor (Live Edge)")
    st.markdown("Monitor siaran langsung kamera lalu lintas DISHUB dengan penanganan latensi rendah.")

    try:
        from config import VEHICLE_LABELS
    except ImportError:
        VEHICLE_LABELS = {0: "Person", 2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}

    # Mengunci URL siaran langsung resmi YouTube DKI Jakarta
    live_url = "https://www.youtube.com/watch?v=AQd-p5hFtQo"
    current_video_id = "AQd-p5hFtQo"

    # Membuat Layout 2 Kolom Utama
    left, right = st.columns([1, 1])

    with left:
        st.subheader("📺 Live Feed Player")
        embed_html = f"""
        <div>
            <iframe width="100%" height="315"
                src="https://www.youtube.com/embed/{current_video_id}?autoplay=1&mute=1&rel=0"
                frameborder="0"
                allow="autoplay; encrypted-media; fullscreen"
                allowfullscreen
                style="border-radius:10px; box-shadow:0 4px 20px rgba(0,0,0,0.3);">
            </iframe>
            <p style="color:gray; font-size:0.82em; margin-top:8px;">
                Mengunci Live Stream: <b>{current_video_id}</b>
            </p>
        </div>
        """
        st.components.v1.html(embed_html, height=350)

    with right:
        st.subheader("🤖 Hasil Deteksi YOLO")

        # Taruh slider di ruang lingkup fungsi agar terbaca oleh fitur uploader di bawahnya
        conf = st.slider("Confidence Threshold", 0.1, 1.0, 0.25, 0.05, key="rt_conf")
        refresh = st.slider("UI Refresh Rate (s)", 0.1, 2.0, 0.5, 0.1, key="rt_refresh")

        is_running_now = st.session_state.get("rt_run", False)

        @st.fragment(run_every=refresh if is_running_now else None)
        def render_ai_stream():
            run = st.toggle("▶ Mulai Deteksi", value=False, key="rt_run")
            
            frame_ph = st.empty()
            stat_ph = st.empty()
            info_ph = st.empty()
            
            if "detector_bridge" not in st.session_state:
                try:
                    from detector import StreamlitDetectorBridge
                    st.session_state.detector_bridge = StreamlitDetectorBridge()
                except ImportError:
                    st.error("Gagal memuat modul 'detector'.")
                    return

            bridge = st.session_state.detector_bridge

            if run:
                if not bridge.is_running:
                    bridge.start(live_url, conf=conf)

                if bridge.error:
                    frame_ph.error(f"Error Deteksi: {bridge.error}")
                elif bridge.latest_frame is not None:
                    with bridge._lock:
                        frame = bridge.latest_frame.copy()
                        stats = bridge.latest_stats.copy()

                    frame_ph.image(frame, channels="RGB", use_container_width=True,
                                   caption=f"AI Monitor Live Edge | Sinkronisasi: {stats.get('ts', '')}")

                    vehicles = {VEHICLE_LABELS.get(k, k): v for k, v in stats.get("vehicles", {}).items()}
                    with stat_ph.container():
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total Objek", stats.get("total", 0))
                        c2.metric("Kendaraan", sum(vehicles.values()))
                        c3.metric("Objek Lain", stats.get("others", 0))
                    
                    if vehicles:
                        info_ph.markdown("📊 **Breakdown:** " + " | ".join(f"**{k}:** {v}" for k, v in vehicles.items()))
                else:
                    frame_ph.info("Menghubungkan ke Live Edge. Menunggu frame pertama...")
            else:
                if bridge.is_running:
                    bridge.stop()
                frame_ph.info("Sistem AI dalam posisi Standby. Aktifkan toggle **Mulai Deteksi** di atas untuk memproses.")

        render_ai_stream()

    # Log Pelanggaran Hari Ini dari Database Resmi
    st.markdown("---")
    st.markdown("#### 🚨 Log Pelanggaran Lalu Lintas Terkini (Database)")
    
    # FIX: Menggunakan fungsi database resmi get_violations_df, bukan load_data bermasalah
    try:
        df_latest = get_violations_df(days_back=1)
    except Exception:
        df_latest = pd.DataFrame()

    if not df_latest.empty:
        target_cols = ['timestamp', 'plate_number', 'vtype_label', 'confidence']
        available_cols = [col for col in target_cols if col in df_latest.columns]
        st.dataframe(df_latest[available_cols].head(5), use_container_width=True)
    else:
        st.info("Belum ada pelanggaran baru yang tercatat masuk ke database hari ini.")

    # Demo Detector Upload — Integrasi Penuh Berantas Deteksi Tumbuhan "Plant" Liar
    st.markdown("---")
    st.subheader("🔍 Demo Detector — Upload Gambar / Video")
    st.caption("Uji deteksi kendaraan & plat nomor menggunakan YOLO + Crop ANPR")

    upload = st.file_uploader("Upload gambar atau video pendek", type=["jpg", "jpeg", "png", "mp4", "avi", "mov"])
    if upload is not None:
        import numpy as np
        from PIL import Image

        if upload.type.startswith("image"):
            img = Image.open(upload).convert("RGB")
            frame_rgb = np.array(img)

            col_ori, col_det = st.columns(2)
            with col_ori:
                st.markdown("**Original**")
                st.image(img, use_container_width=True)
            with col_det:
                st.markdown("**Hasil Deteksi**")
                with st.spinner("Menjalankan detector..."):
                    try:
                        from detector import process_single_frame
                        result = process_single_frame(frame_rgb, conf=conf)
                        v_det = {VEHICLE_LABELS.get(k, k): v for k, v in result["vehicles"].items()}
                        st.image(result["annotated"], channels="RGB", use_container_width=True)
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Terdeteksi", result["total"])
                        c2.metric("Kendaraan", sum(v_det.values()))
                        c3.metric("Lainnya", result["others"])
                    except Exception as e:
                        st.error(f"Detector error: {e}")

            st.markdown("**Deteksi Plat Nomor (ANPR Engine — Crop Mode)**")
            with st.spinner("Membaca plat nomor pada area kendaraan..."):
                try:
                    # FIX: Memanggil ANPRReader bawaan anpr.py Anda untuk mengunci pola plat Indonesia asli
                    from anpr import ANPRReader
                    anpr_reader = ANPRReader()
                    extracted_plate = anpr_reader.read_plate(frame_rgb)
                    
                    if extracted_plate and extracted_plate != "UNKNOWN":
                        st.success(f"Plat terdeteksi (ANPR Engine): **{extracted_plate}**")
                    else:
                        st.info("Tidak ada nomor plat valid (Format Resmi Indonesia) terdeteksi pada objek.")
                except Exception as e:
                    st.error(f"ANPR Engine error: {e}")

# ============================================================
# HALAMAN 7: CONFIGURATION SETTINGS
# ============================================================
def page_settings():
    st.title("⚙️ Pengaturan Sistem & Pemeliharaan")
    st.markdown("Konfigurasi parameter operasional kecerdasan buatan.")

    with st.expander("🛠️ Database Info & Maintenance", expanded=True):
        st.write(f"**Database Path:** `{DB_PATH}`")
        try:
            conn = sqlite3.connect(DB_PATH)
            total = pd.read_sql("SELECT COUNT(*) as count FROM violations", conn).iloc[0]['count']
            conn.close()
        except Exception:
            total = 0
        st.metric("Total Record Database", f"{total:,}")

        st.markdown("---")
        st.subheader("Maintenance")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Clear Cache", use_container_width=True):
                st.cache_data.clear()
                st.success("Cache berhasil dibersihkan.")
        with col_b:
            if st.button("Reset Sample Data", use_container_width=True, type="primary"):
                try:
                    from generate_demo_data import generate_demo_data
                    generate_demo_data(count=300, days_back=30)
                    st.cache_data.clear()
                    st.success("Sample data berhasil di-reset.")
                except Exception as e:
                    st.error(f"Gagal reset data: {e}")

# ============================================================
# MAIN APPLICATION ROUTER
# ============================================================
def main():
    page, days_back = render_navbar()

    # Load shared dataset
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
