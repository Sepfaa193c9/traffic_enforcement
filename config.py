# ============================================================
# config.py — OPTIMIZED for Max Performance (Low CPU/RAM)
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================
# CHANGELOG vs original:
#   - INFERENCE_SIZE    : 640 → 320 (2x faster inference)
#   - FRAME_SKIP        : 1  → 3   (process every 3rd frame)
#   - ANPR_THROTTLE     : 5s → 30s (less OCR = less CPU)
#   - QUEUE_MAXSIZE     : 4  → 2   (less RAM buffering)
#   - YOLO_MODEL        : yolov8s → yolov8n (fastest model)
#   - DISPLAY_SCALE     : NEW 0.75 (smaller window = less GPU/CPU for display)
#   - MAX_TRACKED_OBJECTS: NEW 30  (cap tracker memory)
#   - INFERENCE_HALF    : NEW True (float16 on GPU, ignored on CPU)
# ============================================================

import os

# ------------------------------------------------------------
# VIDEO SOURCE
# ------------------------------------------------------------
VIDEO_SOURCE = 0   # 0=webcam | "file.mp4" | "rtsp://..." | "https://youtu.be/..."

# ------------------------------------------------------------
# YOLO MODEL  ← PILIH SATU
# ------------------------------------------------------------
# yolov8n.pt  — NANO  (~8MB)   ★ PAKAI INI untuk CPU/livestream
# yolov8s.pt  — small (~27MB)  ← GPU terbatas
# yolov8m.pt  — medium (~49MB) ← GPU bagus (T4+)
YOLO_MODEL = "yolov8s.pt"

CONFIDENCE_THRESHOLD = 0.30   # lebih rendah = tangkap kendaraan jauh
IOU_THRESHOLD        = 0.40
INFERENCE_SIZE       = 320    # ★ KUNCI PERFORMA: 320 = 2x lebih cepat dari 640
INFERENCE_HALF       = False  # True = float16 → lebih cepat di GPU CUDA

# ------------------------------------------------------------
# KELAS KENDARAAN (COCO)
# ------------------------------------------------------------
VEHICLE_CLASSES = {
    2: "Mobil",
    3: "Motor",
    5: "Bus",
    7: "Truck",
    1: "Sepeda",
}

# ------------------------------------------------------------
# TRACKING
# ------------------------------------------------------------
TRACK_THRESH  = 0.50
TRACK_BUFFER  = 30
MATCH_THRESH  = 0.80

# ★ Batasi jumlah objek yang di-track agar RAM tidak meledak
MAX_TRACKED_OBJECTS = 50   # buang track lama jika lebih dari ini

# ------------------------------------------------------------
# PELANGGARAN
# ------------------------------------------------------------
ILLEGAL_PARKING_THRESHOLD = 30   # detik sebelum diklasifikasi parkir liar
VIOLATION_COOLDOWN        = 60   # jeda minimum antar pencatatan (detik)

VIOLATION_TYPES = [
    "busway_violation",
    "bike_lane_violation",
    "illegal_parking",
    "wrong_way",
]

# ------------------------------------------------------------
# ZONA DETEKSI  (sesuaikan dengan resolusi kamera Anda)
# ------------------------------------------------------------
ZONES = {
    "busway_sudirman": {
        "polygon": [(0, 400), (200, 400), (200, 500), (0, 500)],
        "violation_type": "busway_violation",
        "color": (0, 0, 255),
    },
    "bike_lane": {
        "polygon": [(600, 350), (800, 350), (800, 450), (600, 450)],
        "violation_type": "bike_lane_violation",
        "color": (0, 255, 0),
    },
    "no_parking_zone": {
        "polygon": [(300, 500), (600, 500), (600, 600), (300, 600)],
        "violation_type": "illegal_parking",
        "color": (0, 165, 255),
    },
}

# ------------------------------------------------------------
# LOKASI KAMERA (GPS)
# ------------------------------------------------------------
CAMERA_LOCATIONS = {
    "CAM_001": {"lat": -6.2088, "lon": 106.8456, "name": "Jl. Sudirman"},
    "CAM_002": {"lat": -6.1751, "lon": 106.8650, "name": "Jl. Thamrin"},
    "CAM_003": {"lat": -6.2146, "lon": 106.8451, "name": "Jl. Gatot Subroto"},
    "CAM_004": {"lat": -6.2297, "lon": 106.8295, "name": "Jl. Tendean"},
    "CAM_005": {"lat": -6.1944, "lon": 106.8229, "name": "Jl. S. Parman"},
}
ACTIVE_CAMERA_ID = "CAM_001"

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "violations.db")

# ★ Write-ahead logging — supaya DB write tidak block inference thread
DB_WAL_MODE = True

# ------------------------------------------------------------
# ANPR
# ------------------------------------------------------------
ANPR_ENABLED    = True          # ★ Matikan jika tidak perlu (hemat ~200MB RAM)
ANPR_LANGUAGES  = ["id", "en"]
ANPR_GPU        = False

ANPR_MIN_PLATE_WIDTH       = 60
ANPR_MIN_PLATE_HEIGHT      = 20
ANPR_CONFIDENCE_THRESHOLD  = 0.40

# ★ Throttle agresif: OCR hanya jalan sekali per 30 detik per kendaraan
ANPR_THROTTLE_SECONDS = 30.0

# ★ Frame cooldown: jangan OCR lebih dari sekali per 15 frame
ANPR_FRAME_COOLDOWN   = 100

ANPR_CACHE_ENABLED    = True     # selalu aktifkan — hemat CPU besar

# ------------------------------------------------------------
# OUTPUT VIDEO
# ------------------------------------------------------------
SAVE_OUTPUT_VIDEO = False
OUTPUT_VIDEO_PATH = "output_annotated.mp4"
OUTPUT_VIDEO_FPS  = 20

# ------------------------------------------------------------
# SPEED ESTIMATOR
# ------------------------------------------------------------
SPEED_PIXELS_PER_METER = 15.0
SPEED_HISTORY_FRAMES   = 8
SPEED_LIMIT_KMH        = 100

# ------------------------------------------------------------
# PERFORMANCE  ★ BAGIAN TERPENTING
# ------------------------------------------------------------

# ★ Proses setiap N frame (1=semua, 3=skip 2, 5=sangat ringan)
#   Untuk CPU tanpa GPU: gunakan 3-5
#   Untuk GPU: bisa 1-2
FRAME_SKIP = 5

# ★ Threaded reader — wajib aktif untuk RTSP/YouTube/HLS
USE_THREADED_READER = True

# ★ Ukuran queue frame (tiap frame ~720p BGR = ~2.8MB)
#   2 frame = ~5.6MB RAM di queue
#   Jangan lebih dari 4 untuk hemat RAM
FRAME_QUEUE_MAXSIZE = 2

# ★ Resize frame SEBELUM masuk queue — hemat RAM & bandwidth memori
#   None = tidak di-resize (gunakan resolusi asli)
#   (1280, 720) = HD, (960, 540) = balanced, (640, 360) = ringan
CAPTURE_RESIZE = (1280, 720)   # selalu normalize ke resolusi ini

# ★ Scale tampilan window (0.75 = 75% ukuran asli) — hemat CPU render
DISPLAY_SCALE = 0.75

# ★ Interval GC (garbage collection) manual — hapus track lama tiap N frame
GC_INTERVAL_FRAMES = 150   # setiap ~5 detik di 30fps

# ★ History posisi per kendaraan — batasi panjangnya
POSITION_HISTORY_MAXLEN = 15

# ------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------
DASHBOARD_PORT      = 8501
DASHBOARD_HOST      = "0.0.0.0"
DASHBOARD_TITLE     = "🚦 DISHUB DKI — Traffic Enforcement System"
DASHBOARD_THEME     = "dark"
DASHBOARD_REFRESH_S = 5

# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------
LOG_LEVEL   = "INFO"
LOG_TO_FILE = False
LOG_FILE    = "traffic_enforcement.log"
