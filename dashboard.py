# ============================================================\n# dashboard.py — Streamlit Dashboard (7 Halaman) - FIXED\n# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026\n# ============================================================\n\nimport time\nimport streamlit as st\nimport pandas as pd\nimport plotly.express as px\nimport plotly.graph_objects as go\nfrom plotly.subplots import make_subplots\nimport folium\nfrom streamlit_folium import st_folium\nfrom datetime import datetime, timedelta\nimport sqlite3\nimport os\nimport sys\n\n# Tambahkan direktori saat ini ke path\nsys.path.insert(0, os.path.dirname(__file__))\n\nfrom config import (\n    DB_PATH, CAMERA_LOCATIONS, DASHBOARD_TITLE,\n    VIOLATION_TYPES, YOLO_MODEL, ACTIVE_CAMERA_ID\n)\nfrom database import (\n    get_violations_df, get_statistics,\n    generate_etl_ticket, get_repeat_offenders,\n    DatabaseManager\n)\n\n# ============================================================\n# AUTO-GENERATE DATABASE JIKA TIDAK ADA\n# ============================================================\n@st.cache_resource\ndef _init_database():\n    \"\"\"Initialize database with sample data if not exists\"\"\"\n    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 5000:\n        try:\n            print(\"[*] Database kosong, insert sample data...\")\n            from generate_demo_data import generate_demo_data\n            generate_demo_data(count=300, days_back=30)\n            print(\"[✓] Sample data inserted\")\n            return True\n        except Exception as e:\n            print(f\"[!] Gagal membuat data simulasi: {e}\")\n    return False\n\n_init_database()\n\n# ============================================================\n# DATA LOADERS WITH CACHE\n# ============================================================\n@st.cache_data(ttl=5)  # Cache 5 detik agar responsif tapi tidak membebani disk\ndef load_data(days_back=7):\n    return get_violations_df(days_back=days_back)\n\n@st.cache_data(ttl=5)\ndef load_stats(days_back=7):\n    return get_statistics(days_back=days_back)\n\n# ============================================================\n# NAVIGATION BAR\n# ============================================================\ndef render_navbar():\n    st.sidebar.image(\n        \"https://upload.wikimedia.org/wikipedia/commons/b/b4/Logo_Dishub_DKI_Jakarta.png\",\n        width=90\n    )\n    st.sidebar.title("🚨 DISHUB DKI Jakarta")\n    st.sidebar.subheader("Traffic Enforcement AI")\n    \n    st.sidebar.markdown("---")\n    \n    page = st.sidebar.radio(\n        "Menu Navigasi",\n        [\n            "Dashboard", \n            "Analytics", \n            "E-TLE Integration", \n            "Reports", \n            "Heatmap", \n            "Real-time Monitor", \n            "Settings"\n        ]\n    )\n    \n    st.sidebar.markdown("---")\n    days_back = st.sidebar.slider("Rentang Data (Hari Terakhir)", 1, 90, 7)\n    \n    st.sidebar.markdown("---")\n    st.sidebar.info(\n        "📊 **Sistem Aktif**\\n" \n        "Engine: YOLOv8 + EasyOCR\\n" \n        "Status Platform: Operational Platform"\n    )\n    \n    return page, days_back\n\n# ============================================================\n# HALAMAN 6: REAL-TIME MONITOR (HALAMAN YANG EROR & SUDAH DI-FIX)\n# ============================================================\ndef page_realtime():\n    st.header("🎥 Real-time Video Monitor (Live Edge)")\n    st.markdown("Monitor siaran langsung kamera lalu lintas DISHUB dengan penanganan latensi rendah.")\n\n    # Fallback variabel jika config.py tidak terbaca\n    try:\n        from config import VEHICLE_LABELS\n    except ImportError:\n        VEHICLE_LABELS = {0: "Person", 2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}\n\n    # Mengunci URL langsung sesuai permintaan Anda\n    live_url = "https://www.youtube.com/watch?v=AQd-p5hFtQo"\n    current_video_id = "AQd-p5hFtQo"\n\n    # 1. MEMBUAT LAYOUT UTAMA (2 KOLOM)\n    left, right = st.columns([1, 1])\n\n    # ── SISI KIRI: Embed Player Live Youtube ──────────────────────────────────\n    with left:\n        st.subheader("📺 Live Feed Player")\n        embed_html = f\"\"\"\n        <div>\n            <iframe width=\"100%\" height=\"315\"\n                src=\"https://www.youtube.com/embed/{current_video_id}?autoplay=1&mute=1&rel=0\"\n                frameborder=\"0\"\n                allow=\"autoplay; encrypted-media; fullscreen\"\n                allowfullscreen\n                style=\"border-radius:10px; box-shadow:0 4px 20px rgba(0,0,0,0.3);\">\n            </iframe>\n            <p style=\"color:gray; font-size:0.82em; margin-top:8px;\">\n                Mengunci Live Stream: <b>{current_video_id}</b>\n            </p>\n        </div>\n        \"\"\"\n        st.components.v1.html(embed_html, height=350)\n\n    # ── SISI KANAN: Hasil Pemrosesan Frame AI + TOGGLE CONTROL ────────────────\n    with right:\n        st.subheader("🤖 Hasil Deteksi YOLO")\n\n        # Definisikan conf & refresh di luar fragment agar bisa diakses oleh fungsi demo upload\n        conf = st.slider("Confidence Threshold", 0.1, 1.0, 0.25, 0.05, key="rt_conf")\n        refresh = st.slider("UI Refresh Rate (s)", 0.1, 2.0, 0.5, 0.1, key="rt_refresh")\n\n        is_running_now = st.session_state.get("rt_run", False)\n\n        @st.fragment(run_every=refresh if is_running_now else None)\n        def render_ai_stream():\n            run = st.toggle("▶ Mulai Deteksi", value=False, key="rt_run")\n            \n            frame_ph = st.empty()\n            stat_ph = st.empty()\n            info_ph = st.empty()\n            \n            if "detector_bridge" not in st.session_state:\n                try:\n                    from detector import StreamlitDetectorBridge\n                    st.session_state.detector_bridge = StreamlitDetectorBridge()\n                except ImportError:\n                    st.error("Gagal memuat modul 'detector'.")\n                    return\n\n            bridge = st.session_state.detector_bridge\n\n            if run:\n                if not bridge.is_running:\n                    bridge.start(live_url, conf=conf)\n\n                if bridge.error:\n                    frame_ph.error(f"Error Deteksi: {bridge.error}")\n                elif bridge.latest_frame is not None:\n                    with bridge._lock:\n                        frame = bridge.latest_frame.copy()\n                        stats = bridge.latest_stats.copy()\n\n                    frame_ph.image(frame, channels="RGB", use_container_width=True,\n                                   caption=f"AI Monitor Live Edge | Sinkronisasi: {stats.get('ts', '')}")\n\n                    vehicles = {VEHICLE_LABELS.get(k, k): v for k, v in stats.get("vehicles", {}).items()}\n                    with stat_ph.container():\n                        c1, c2, c3 = st.columns(3)\n                        c1.metric("Total Objek", stats.get("total", 0))\n                        c2.metric("Kendaraan", sum(vehicles.values()))\n                        c3.metric("Objek Lain", stats.get("others", 0))\n                    \n                    if vehicles:\n                        info_ph.markdown("📊 **Breakdown:** " + " | ".join(f"**{k}:** {v}" for k, v in vehicles.items()))\n                else:\n                    frame_ph.info("Menghubungkan ke Live Edge. Menunggu frame pertama...")\n            else:\n                if bridge.is_running:\n                    bridge.stop()\n                frame_ph.info("Sistem AI dalam posisi Standby. Aktifkan toggle **Mulai Deteksi** di atas untuk memproses.")\n\n        render_ai_stream()\n\n    # ── BAGIAN BAWAH: Log Pelanggaran Terdeteksi Terkini (Database Resmi) ──\n    st.markdown("---")\n    st.markdown("#### 🚨 Log Pelanggaran Lalu Lintas Terkini (Database)")\n    \n    # FIX: Menggunakan get_violations_df dari database.py, bukan load_data yang memicu NameError\n    try:\n        df_latest = get_violations_df(days_back=1)\n    except Exception:\n        df_latest = pd.DataFrame()\n\n    if not df_latest.empty:\n        target_cols = ['timestamp', 'plate', 'vtype_label', 'confidence']\n        available_cols = [col for col in target_cols if col in df_latest.columns]\n        \n        if 'plate' not in df_latest.columns and 'plate_number' in df_latest.columns:\n            available_cols.append('plate_number')\n        if 'vtype_label' not in df_latest.columns and 'violation_type' in df_latest.columns:\n            available_cols.append('violation_type')\n\n        if available_cols:\n            st.dataframe(df_latest[available_cols].head(5), use_container_width=True)\n        else:\n            st.dataframe(df_latest.head(5), use_container_width=True)\n    else:\n        st.info("Belum ada pelanggaran baru yang tercatat masuk ke database hari ini.")\n\n    # ── SECTION: Demo Detector (Fix Masalah Deteksi \"Plant\" Daun / Background) ──\n    st.markdown("---")\n    st.subheader("🔍 Demo Detector — Upload Gambar / Video")\n    st.caption("Uji deteksi kendaraan & plat nomor menggunakan YOLO + Crop ANPR")\n\n    upload = st.file_uploader("Upload gambar atau video pendek", type=["jpg", "jpeg", "png", "mp4", "avi", "mov"])\n    if upload is not None:\n        import numpy as np\n        from PIL import Image\n\n        if upload.type.startswith("image"):\n            img = Image.open(upload).convert("RGB")\n            frame_rgb = np.array(img)\n\n            col_ori, col_det = st.columns(2)\n            with col_ori:\n                st.markdown("**Original**")\n                st.image(img, use_container_width=True)\n            with col_det:\n                st.markdown("**Hasil Deteksi**")\n                with st.spinner("Menjalankan detector..."):\n                    try:\n                        from detector import process_single_frame\n                        result = process_single_frame(frame_rgb, conf=conf)\n                        v_det = {VEHICLE_LABELS.get(k, k): v for k, v in result["vehicles"].items()}\n                        st.image(result["annotated"], channels="RGB", use_container_width=True)\n                        \n                        c1, c2, c3 = st.columns(3)\n                        c1.metric("Terdeteksi", result["total"])
                        c2.metric("Kendaraan", sum(v_det.values()))
                        c3.metric("Lainnya", result["others"])
                    except Exception as e:
                        st.error(f"Detector error: {e}")

            st.markdown("**Deteksi Plat Nomor (ANPR Engine — Crop Mode)**")
            with st.spinner("Membaca plat nomor pada area kendaraan..."):
                try:
                    # FIX: Memanggil ANPRReader resmi dari anpr.py milik Anda sendiri
                    # Hal ini mencegah EasyOCR membaca background pohon/pot secara liar
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
# STUBS/PLACEHOLDERS UNTUK HALAMAN LAIN (AGAR TIDAK ERROR)
# ============================================================
def page_dashboard(df, stats):
    st.title("📊 Dashboard Utama")
    st.write("Statistik ringkasan pelanggaran lalu lintas.")
    st.dataframe(df.head(10))

def page_analytics(df, days_back):
    st.title("📈 Analytics & Tren")
    st.write("Analisis tren pelanggaran.")

def page_etle(df):
    st.title("✉️ Integrasi E-TLE")
    st.write("Penerbitan surat konfirmasi pelanggaran otomatis.")

def page_reports(df, days_back):
    st.title("📋 Laporan Pelanggaran")
    st.write("Unduh data dan ekspor laporan berkala.")

def page_heatmap(df):
    st.title("🗺️ Peta Titik Rawan (Heatmap)")
    st.write("Lokasi dengan frekuensi pelanggaran tertinggi.")

def page_settings():
    st.title("⚙️ Pengaturan Sistem")
    st.write("Konfigurasi parameter AI dan integrasi database.")

# ============================================================
# MAIN INFERENCE LOOP
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
