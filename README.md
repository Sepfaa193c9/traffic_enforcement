# DISHUB DKI Jakarta - Intelligent Traffic Enforcement System

Sistem otomatis untuk deteksi, tracking, dan analisis pelanggaran lalu lintas menggunakan **AI dan Computer Vision**.
## Fitur Utama

**Real-time Detection** — Deteksi pelanggaran via CCTV menggunakan YOLOv8  
**ANPR (License Plate Reading)** — Baca plat nomor otomatis dengan EasyOCR  
**Multi-Object Tracking** — Track kendaraan dengan ByteTrack untuk hitung durasi  
**Zone Detection** — Deteksi masuk jalur busway, jalur sepeda, atau parkir liar  
**Spatial-Temporal Heatmap** — Visualisasi hotspot pelanggaran di peta Jakarta  
**E-TLE Integration** — Database pelanggaran untuk electronic ticketing  
**Analytics Dashboard** — Streamlit dashboard dengan 7 halaman analitik  
**Excel Report Generator** — Laporan resmi multi-sheet siap cetak  
YOLOv8, OpenCV, SQLite, Streamlit, Plotly, Folium semua gratis

---

## Tech Stack

| Komponen | Technology | Status |
|----------|-----------|--------|
| **Object Detection** | YOLOv8 (Ultralytics) | ✅ Free |
| **License Plate Recognition** | EasyOCR | ✅ Free |
| **Multi-Object Tracking** | ByteTrack (Supervision) | ✅ Free |
| **Database** | SQLite (built-in Python) | ✅ Free |
| **Dashboard** | Streamlit | ✅ Free |
| **Maps** | Folium | ✅ Free |
| **Charts** | Plotly | ✅ Free |
| **Reports** | OpenPyXL | ✅ Free |

**Total cost: $0** ✅

---

## Instalasi

### 1. Clone Repository & Setup Virtual Environment

```bash
# Buat folder proyek
mkdir traffic_enforcement
cd traffic_enforcement

# Virtual environment (recommended)
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
# Download requirements.txt (atau copy dari project)
pip install -r requirements.txt
```

**Proses instalasi pertama kali akan:**
- Download YOLOv8 model (~25MB untuk nano, ~75MB untuk small)
- Download EasyOCR model (~200MB, sekali saja)
- Buat database SQLite otomatis

Estimasi waktu: 5-10 menit (tergantung koneksi internet)

---

## Quickstart (5 Menit)

### A. Generate Data Demo & Jalankan Dashboard

```bash
# Terminal 1: Generate 300 data pelanggaran sintetis untuk testing
python generate_demo_data.py --count 300 --days 30

# Terminal 2: Jalankan dashboard
streamlit run dashboard.py
```

Dashboard akan buka di `http://localhost:8501`

Selesai! Sekarang kamu punya dashboard dengan data testing.

### B. Jalankan Deteksi Real-time (dari webcam)

```bash
python detector.py
```

Tekan `Q` untuk stop, `S` untuk screenshot.

### C. Generate Laporan Excel

```bash
# Generate laporan 30 hari terakhir
python report_generator.py

# Atau custom days
python report_generator.py --days 7 --output laporan_minggu.xlsx
```

Laporan akan tersimpan sebagai `Laporan_DISHUB_YYYYMMDD.xlsx`

---

## Panduan Penggunaan Lengkap

### Setup Zona Deteksi (Konfigurasi Awal)

Sebelum production, kamu perlu configure zona untuk busway, jalur sepeda, dan parkir liar.

```bash
# Tool interaktif untuk menggambar zona
python zone_configurator.py --source video.mp4
# Atau untuk webcam:
python zone_configurator.py
```

**Cara menggunakan:**
1. Klik kiri → Tambah titik zona (minimal 3 titik)
2. Tekan SPACE → Selesai zona, mulai zona baru
3. Tekan S → Simpan & copy output
4. Paste output ke `ZONES` di `config.py`
5. Edit `violation_type` untuk setiap zona

### Config.py - Konfigurasi Utama

Edit file `config.py` untuk:

```python
# Video source
VIDEO_SOURCE = 0  # 0=webcam, atau path file, atau RTSP URL

# Model YOLO (balance akurasi vs kecepatan)
YOLO_MODEL = "yolov8n.pt"  # nano (cepat), small (seimbang), medium (akurat)

# Threshold parkir liar (detik)
ILLEGAL_PARKING_THRESHOLD = 30  # production: 30s, demo: 10s

# Lokasi kamera (GPS)
CAMERA_LOCATIONS = {
    "CAM_001": {"lat": -6.2088, "lon": 106.8456, "name": "Jl. Sudirman"},
    # ... tambah kamera lainnya
}

# Zona deteksi (output dari zone_configurator.py)
ZONES = {
    "busway": {
        "polygon": [(0,400), (400,400), (400,500), (0,500)],
        "violation_type": "busway_violation"
    },
    # ... dll
}
```

### Dashboard Streamlit

Jalankan dashboard dengan:

```bash
streamlit run dashboard.py
```

**Halaman-halaman:**
1. 📊 **Dashboard** — Overview dengan metric cards, heatmap, dan recent violations
2. 📈 **Analytics** — Analisis mendalam (hourly patterns, vehicle types, recidivism)
3. 🎫 **E-TLE Integration** — Database pelanggaran + tombol generate tiket
4. 📋 **Reports** — Generator laporan Excel
5. 🗺️ **Heatmap** — Peta interaktif dengan distribusi hotspot
6. 📱 **Real-time Monitor** — Live stream (jika detector.py berjalan)
7. ⚙️ **Settings** — Konfigurasi sistem & info teknis

### Detector.py - Jalankan Deteksi

```bash
# Dari webcam (real-time)
python detector.py

# Dari file video
# Edit di config.py: VIDEO_SOURCE = "traffic_video.mp4"

# Dari CCTV/IP Camera (RTSP)
# Edit di config.py: VIDEO_SOURCE = "rtsp://192.168.1.100:554/stream"
```

**Kontrol:**
- Tekan `Q` → Berhenti
- Tekan `S` → Screenshot
- Tekan `P` → Pause

Output video dengan annotasi akan tersimpan (opsional di code).

### Report Generator

```bash
# Generate laporan 30 hari
python report_generator.py

# Custom rentang waktu
python report_generator.py --days 7

# Custom output filename
python report_generator.py --output laporan_custom.xlsx
```

Laporan mencakup:
- ✅ Ringkasan eksekutif dengan metric utama
- ✅ Data pelanggaran lengkap
- ✅ Analisis per kamera
- ✅ Pola waktu (jam, hari dalam minggu)
- ✅ Tren harian (line chart)
- ✅ Pelanggar berulang dengan risk level
- ✅ Status E-TLE (sudah/belum ditilang)

---

## 📂 Struktur File Proyek

```
traffic_enforcement/
├── config.py                    # ⚙️ Konfigurasi utama (EDIT INI!)
├── detector.py                  # 🎥 Engine deteksi YOLOv8 + ByteTrack
├── anpr.py                      # 🔤 Baca plat nomor EasyOCR
├── database.py                  # 🗄️ SQLite database manager
├── analytics.py                 # 📊 Fungsi analitik untuk dashboard
├── dashboard.py                 # 📈 Streamlit dashboard (7 halaman)
├── report_generator.py          # 📋 Generate laporan Excel
├── zone_configurator.py         # 🎮 Tool konfigurasi zona interaktif
├── generate_demo_data.py        # 🎲 Generator data testing
├── requirements.txt             # 📦 Dependencies
├── violations.db                # 🗄️ Database SQLite (auto-dibuat)
└── README.md                    # 📖 File ini
```

---

## 🚀 Production Tips

### 1. Gunakan Model YOLO yang Lebih Akurat

```python
# config.py
YOLO_MODEL = "yolov8s.pt"  # atau yolov8m.pt untuk akurasi tertinggi
```

Perbandingan:
- **nano** (8MB): Tercepat, cocok untuk edge devices
- **small** (27MB): Seimbang (rekomendasi)
- **medium** (49MB): Paling akurat

### 2. Setup Auto-Start di Server

```bash
# Create systemd service (Linux)
sudo nano /etc/systemd/system/traffic-enforcement.service

[Unit]
Description=Traffic Enforcement System
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/traffic_enforcement
ExecStart=/home/your_user/traffic_enforcement/venv/bin/python detector.py
Restart=always

[Install]
WantedBy=multi-user.target

# Enable & start
sudo systemctl enable traffic-enforcement
sudo systemctl start traffic-enforcement
sudo systemctl status traffic-enforcement
```

### 3. Backup Database Harian

```bash
# Cron job (Linux) - backup every day at 2 AM
0 2 * * * cp /path/to/violations.db /path/to/backup/violations_$(date +\%Y\%m\%d).db
```

### 4. Deploy Dashboard di Server

```bash
# Jalankan dengan SSL & authentication
streamlit run dashboard.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --logger.level=info
```

### 5. Monitor Performance

```python
# Check database size
python -c "
import os
db_path = 'violations.db'
size_mb = os.path.getsize(db_path) / 1024 / 1024
print(f'Database size: {size_mb:.1f} MB')
"

# Monitor detector.py dengan htop
htop
```

---

## 🐛 Troubleshooting

### Error: "ModuleNotFoundError: No module named 'ultralytics'"

```bash
pip install --upgrade ultralytics
```

### Error: "CUDA not found" (GPU)

Sistem otomatis fallback ke CPU. Instalasi CUDA jika punya GPU NVIDIA:

```bash
pip install ultralytics[gpu]  # Automatic CUDA detection
```

### Error: "EasyOCR download timeout"

EasyOCR besar (~200MB), download bisa timeout:

```bash
# Manual download
python -c "import easyocr; easyocr.Reader(['id', 'en'])"
```

### Dashboard: "Module analytics tidak ditemukan"

Pastikan semua file `.py` ada di direktori sama:

```bash
ls -la
# Harus ada: config.py, database.py, analytics.py, dashboard.py, dll
```

### Deteksi lambat / lag

Turunkan resolusi atau gunakan model lebih kecil:

```python
# config.py
YOLO_MODEL = "yolov8n.pt"  # Gunakan nano
CONFIDENCE_THRESHOLD = 0.4  # Turunkan threshold

# detector.py
results = model(frame, conf=CONFIDENCE_THRESHOLD, imgsz=480)  # Kecilkan resolusi
```

---

## 📊 Sample Output

### Dashboard Output

- **Metric Cards**: Total violations, per violation type, average duration
- **Heatmap**: Distribusi geografis pelanggaran dengan marker interaktif
- **Charts**: Pie chart (violation types), bar chart (vehicle types), line chart (hourly trend)
- **Recent Violations Table**: Tabel live dengan tombol E-TLE ticketing
- **Top Offenders**: Daftar pelanggar berulang dengan risk level

### Report Output (Excel)

Sheet 1: **Ringkasan Eksekutif** — Cover + metric utama  
Sheet 2: **Data Pelanggaran** — Tabel lengkap dengan filter  
Sheet 3: **Per Kamera** — Analisis per lokasi kamera  
Sheet 4: **Pola Waktu** — Hourly distribution heatmap  
Sheet 5: **Tren Harian** — Line chart 30 hari terakhir  
Sheet 6: **Pelanggar Berulang** — Recidivism analysis + pie chart  
Sheet 7: **Status E-TLE** — Tiket yang sudah/belum diterbitkan  

---

## 📚 Dokumentasi Lanjutan

### Import Modules dari Code Lain

```python
from detector import TrafficEnforcementSystem
from database import get_violations_df, get_statistics
from analytics import get_peak_violation_hours, get_camera_hotspots
from report_generator import generate_report

# Contoh: Generate report dari Python
report_bytes = generate_report(
    days_back=7,
    to_bytes=True  # Return bytes, bukan file
)
```

### Integrasi dengan Sistem DISHUB Existing

Database struktur bisa di-export ke API:

```python
# API endpoint untuk sistem E-TLE
@app.post("/api/violations")
def create_violation(data: dict):
    from database import save_violation
    save_violation(data)
    return {"status": "success"}

@app.get("/api/violations/{plate}")
def get_vehicle_violations(plate: str):
    from database import get_violations_df
    df = get_violations_df()
    return df[df["license_plate"] == plate].to_dict()
```

---

## 🤝 Contributing & Feedback

Sistem ini dibuat untuk **AI Open Innovation Challenge 2026** oleh DISHUB DKI Jakarta.

Untuk improvement atau bug report, silakan:
1. Fork repository
2. Buat branch feature
3. Submit pull request

---

## 📞 Support & Info

- **Database**: SQLite `violations.db` (binary format)
- **Config**: Edit `config.py` untuk customize
- **Logs**: Console output real-time saat `detector.py` berjalan
- **Settings**: Settings halaman di dashboard Streamlit

---

## 📄 License

MIT License - Gratis untuk penggunaan komersial maupun non-komersial

---

## 🎉 Terima Kasih!

Built with ❤️ menggunakan:
- **YOLOv8** (Ultralytics)
- **ByteTrack** (Roboflow Supervision)
- **EasyOCR** (JaidedAI)
- **Streamlit** (Streamlit Inc)
- **Folium** (Leaflet contributors)
- **Plotly** (Plotly)
- **SQLite** (SQLite Consortium)

Semua tools **100% FREE & OPEN SOURCE** 🎉

---

**Last Updated**: May 2026  
**Version**: 1.1.0  
**Status**: Production Ready ✅
