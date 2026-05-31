# ============================================================
# detector.py — Engine Deteksi OPTIMIZED (Low CPU/RAM)
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================
"""
Perubahan vs versi original:
  ★ FRAME RESIZE sebelum queue → hemat RAM signifikan
  ★ QUEUE maxsize=2 → tidak timbun frame di memory
  ★ INFERENCE HALF (float16) → 30-50% lebih cepat di GPU
  ★ DISPLAY SCALE → window kecil, render lebih ringan
  ★ GC MANUAL → hapus track lama tiap N frame
  ★ DB write via background thread → inference tidak blocking
  ★ ANPR async thread pool → tidak blocking main loop
  ★ RAM GUARD: cap history posisi & jumlah track
  ★ cv2.imshow non-blocking dengan waitKey(1)
  ★ Model warmup → inference pertama tidak lag
  ★ Headless mode (--no-display) untuk server/cloud

Usage:
    python detector.py                                    # Webcam + display
    python detector.py --source video.mp4                 # File video
    python detector.py --source rtsp://192.168.1.1/stream # RTSP/CCTV
    python detector.py --source "https://youtu.be/XXXX"  # YouTube
    python detector.py --no-display                       # Headless (server/cloud)
    python detector.py --frame-skip 5                     # Override frame skip

Kontrol:
    Q → Berhenti
    S → Screenshot
    P → Pause/Resume
"""

import argparse
import gc
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# DEPENDENCY CHECK
# ============================================================

def _check_imports() -> dict:
    status = {}
    try:
        from ultralytics import YOLO          # noqa: F401
        status["yolo"] = True
    except ImportError:
        status["yolo"] = False
        logger.error("YOLOv8 tidak tersedia. Jalankan: pip install ultralytics")

    try:
        import supervision as sv              # noqa: F401
        status["supervision"] = True
    except ImportError:
        status["supervision"] = False
        logger.error("Supervision tidak tersedia.")

    try:
        from trackers import ByteTrackTracker  # noqa: F401
        status["trackers"] = True
    except ImportError:
        if status.get("supervision"):
            status["trackers"] = True
            logger.warning("trackers tidak tersedia, akan gunakan fallback supervision.ByteTrack")
        else:
            status["trackers"] = False
            logger.error("trackers tidak tersedia.")

    return status

# Tambahkan di bagian import (setelah import lainnya)
# ============================================================
# FIX: Pastikan semua module bisa diimport dengan benar
# ============================================================

# Fix for trackers import
try:
    from trackers import ByteTrackTracker
except ImportError:
    # Fallback: gunakan supervision ByteTrack
    try:
        from supervision.tracker import ByteTrack
        class ByteTrackTracker:
            def __init__(self):
                self.tracker = ByteTrack()
            def update(self, detections):
                return self.tracker.update_with_detections(detections)
    except ImportError:
        logger.warning("ByteTrack tidak tersedia, tracking dinonaktifkan")
        ByteTrackTracker = None
# ============================================================
# STREAM HELPERS
# ============================================================

def is_youtube_url(url: str) -> bool:
    return any(d in url for d in (
        "youtube.com/watch", "youtube.com/live",
        "youtu.be/", "youtube.com/shorts",
    ))


def get_youtube_stream_url(youtube_url: str) -> str:
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp tidak ditemukan. Install: pip install yt-dlp")

    print("Mengambil stream URL (5-15 detik)...")
    fmt = "best[height<=720][ext=mp4]/best[height<=720]/best"
    cmd = ["yt-dlp", "-g", "-f", fmt, "--no-warnings", "--no-playlist", youtube_url]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timeout. Cek koneksi atau coba URL lain.")

    if res.returncode != 0:
        raise RuntimeError(f"yt-dlp error: {res.stderr.strip() or res.stdout.strip()}")

    urls = [u.strip() for u in res.stdout.strip().splitlines() if u.strip()]
    if not urls:
        raise RuntimeError("yt-dlp tidak mengembalikan URL.")

    print(f"[yt-dlp] OK — {len(urls)} stream tersedia")
    return urls[0]


def is_hls_url(url: str) -> bool:
    return isinstance(url, str) and ".m3u8" in url


# ============================================================
# ZONE POLYGON HELPERS
# ============================================================

def point_in_polygon(point: tuple, polygon: list) -> bool:
    x, y = point
    n    = len(polygon)
    inside = False
    px, py = polygon[0]
    for i in range(1, n + 1):
        qx, qy = polygon[i % n]
        if ((py > y) != (qy > y)) and (x < (qx - px) * (y - py) / (qy - py) + px):
            inside = not inside
        px, py = qx, qy
    return inside


def get_bbox_bottom_center(x1, y1, x2, y2) -> tuple:
    return ((x1 + x2) // 2, y2)


# ============================================================
# VISUALIZATION HELPERS
# ============================================================

VIOLATION_COLORS = {
    "busway_violation":    (0,   0, 255),
    "bike_lane_violation": (0, 165, 255),
    "illegal_parking":     (0,   0, 200),
    "wrong_way":           (255,  0, 255),
    "zone_violation":      (0, 200, 255),
}
_DEFAULT_VIOLATION_COLOR = (0, 165, 255)


def get_violation_color(vtype: str) -> tuple:
    return VIOLATION_COLORS.get(vtype, _DEFAULT_VIOLATION_COLOR)


def draw_zones(frame: np.ndarray, zones: dict) -> np.ndarray:
    overlay = frame.copy()
    for zinfo in zones.values():
        poly  = np.array(zinfo["polygon"], dtype=np.int32)
        color = zinfo.get("color", (0, 255, 255))
        cv2.fillPoly(overlay, [poly], color)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    for zname, zinfo in zones.items():
        poly  = np.array(zinfo["polygon"], dtype=np.int32)
        color = zinfo.get("color", (0, 255, 255))
        cv2.polylines(frame, [poly], True, color, 2)

        cx = int(np.mean([p[0] for p in zinfo["polygon"]]))
        cy = int(np.mean([p[1] for p in zinfo["polygon"]]))
        (tw, th), _ = cv2.getTextSize(zname, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)
        cv2.rectangle(frame, (cx - tw//2 - 4, cy - th - 4),
                              (cx + tw//2 + 4, cy + 4), (0, 0, 0), -1)
        cv2.putText(frame, zname, (cx - tw//2, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2, cv2.LINE_AA)
    return frame


def draw_zone_active_highlight(frame: np.ndarray, polygon: list, intensity: float = 0.22):
    overlay = frame.copy()
    poly = np.array(polygon, dtype=np.int32)
    cv2.fillPoly(overlay, [poly], (30, 30, 220))
    cv2.addWeighted(overlay, intensity, frame, 1.0 - intensity, 0, frame)


def draw_hitbox(frame: np.ndarray, center: tuple, in_violation: bool):
    x, y = center
    if in_violation:
        cv2.circle(frame, (x, y), 5,  (0, 0, 255), -1)
        cv2.circle(frame, (x, y), 10, (0, 0, 255), 2)
        cv2.line(frame, (x-14, y), (x+14, y), (0, 0, 255), 1)
        cv2.line(frame, (x, y-14), (x, y+14), (0, 0, 255), 1)
    else:
        cv2.circle(frame, (x, y), 3,  (0, 255, 0), -1)
        cv2.circle(frame, (x, y), 7,  (0, 255, 0), 1)
        cv2.line(frame, (x-9, y), (x+9, y), (0, 200, 0), 1)
        cv2.line(frame, (x, y-9), (x, y+9), (0, 200, 0), 1)


def draw_bbox_label(frame: np.ndarray, bbox: tuple, label: str,
                    color: tuple, thickness: int = 2):
    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

    font, fscale, fthick = cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
    (tw, th), bl = cv2.getTextSize(label, font, fscale, fthick)
    pad = 3
    ly1 = max(y1 - th - bl - pad*2, 0)
    cv2.rectangle(frame, (x1, ly1), (x1 + tw + pad*2, y1), color, -1)
    cv2.putText(frame, label, (x1 + pad, y1 - bl - pad//2),
                font, fscale, (255, 255, 255), fthick, cv2.LINE_AA)


def draw_violation_box(frame: np.ndarray, bbox: tuple, label: str,
                       vtype: str, duration: float):
    x1, y1, x2, y2 = bbox
    color = get_violation_color(vtype)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
    cv2.rectangle(frame, (x1+4, y1+4), (x2-4, y2-4), color, 1)
    draw_bbox_label(frame, bbox, label, color, thickness=0)

    if duration > 0:
        dtxt = f"Dur: {duration:.0f}s"
        font = cv2.FONT_HERSHEY_SIMPLEX
        (dw, dh), _ = cv2.getTextSize(dtxt, font, 0.42, 1)
        cv2.rectangle(frame, (x1, y2+2), (x1+dw+6, y2+dh+10), (0, 0, 0), -1)
        cv2.putText(frame, dtxt, (x1+3, y2+dh+4),
                    font, 0.42, color, 1, cv2.LINE_AA)


def draw_proximity_warning(frame: np.ndarray, center: tuple, zones: dict):
    for zinfo in zones.values():
        poly = np.array(zinfo["polygon"], dtype=np.int32)
        dist = cv2.pointPolygonTest(poly, (float(center[0]), float(center[1])), True)
        if -80 < dist < -5:
            cv2.circle(frame, center, 22, (0, 165, 255), 2)
            cv2.circle(frame, center, 32, (0, 165, 255), 1)
            txt  = "NEAR ZONE"
            font = cv2.FONT_HERSHEY_SIMPLEX
            (tw, th), _ = cv2.getTextSize(txt, font, 0.46, 1)
            tx, ty = center[0] - tw//2, center[1] - 40
            cv2.rectangle(frame, (tx-3, ty-th-2), (tx+tw+3, ty+3), (0,0,0), -1)
            cv2.putText(frame, txt, (tx, ty), font, 0.46, (0,165,255), 1, cv2.LINE_AA)


def draw_direction_arrow(frame: np.ndarray, track_id: int,
                         curr: tuple, prev_positions: dict, color: tuple):
    if track_id not in prev_positions or len(prev_positions[track_id]) < 2:
        return
    prev = prev_positions[track_id][0]
    dx, dy = curr[0] - prev[0], curr[1] - prev[1]
    if abs(dx) > 2 or abs(dy) > 2:
        mag = np.sqrt(dx**2 + dy**2)
        ex  = int(curr[0] + dx/mag * 36)
        ey  = int(curr[1] + dy/mag * 36)
        cv2.arrowedLine(frame, curr, (ex, ey), color, 2, tipLength=0.38)


# ============================================================
# ASYNC DB WRITER — inference tidak pernah tunggu disk
# ============================================================

class AsyncDBWriter:
    """
    Tulis violation ke DB di background thread.
    Main loop tidak pernah block menunggu SQLite.
    """
    def __init__(self, db):
        self._db    = db
        self._queue = queue.Queue(maxsize=200)  # buffer 200 event
        self._t     = threading.Thread(target=self._worker, daemon=True)
        self._t.start()

    def write(self, record: dict):
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            logger.warning("DB write queue full — violation dropped")

    def _worker(self):
        while True:
            record = self._queue.get()
            try:
                self._db.save_violation(record)
            except Exception as e:
                logger.error(f"DB write error: {e}")
            self._queue.task_done()


# ============================================================
# TRAFFIC ENFORCEMENT SYSTEM — OPTIMIZED
# ============================================================

class TrafficEnforcementSystem:
    """
    Sistem utama — dioptimasi untuk CPU/RAM rendah.
    """

    def __init__(self, source=None, no_display: bool = False,
                 frame_skip_override: int = None):
        from config import (
            YOLO_MODEL, CONFIDENCE_THRESHOLD, IOU_THRESHOLD,
            INFERENCE_SIZE, INFERENCE_HALF, VEHICLE_CLASSES,
            ZONES, ACTIVE_CAMERA_ID, CAMERA_LOCATIONS,
            ILLEGAL_PARKING_THRESHOLD, VIOLATION_COOLDOWN,
            SAVE_OUTPUT_VIDEO, OUTPUT_VIDEO_PATH, OUTPUT_VIDEO_FPS,
            ANPR_ENABLED, VIDEO_SOURCE,
            FRAME_SKIP, USE_THREADED_READER, FRAME_QUEUE_MAXSIZE,
            CAPTURE_RESIZE, DISPLAY_SCALE,
            GC_INTERVAL_FRAMES, MAX_TRACKED_OBJECTS,
            POSITION_HISTORY_MAXLEN, DB_WAL_MODE,
        )

        self.source            = source if source is not None else VIDEO_SOURCE
        self.vehicle_classes   = VEHICLE_CLASSES
        self.zones             = ZONES
        self.camera_id         = ACTIVE_CAMERA_ID
        self.cam_info          = CAMERA_LOCATIONS.get(ACTIVE_CAMERA_ID, {})
        self.parking_threshold = ILLEGAL_PARKING_THRESHOLD
        self.violation_cooldown = VIOLATION_COOLDOWN
        self.conf              = CONFIDENCE_THRESHOLD
        self.iou               = IOU_THRESHOLD
        self.imgsz             = INFERENCE_SIZE
        self.infer_half        = INFERENCE_HALF
        self.save_video        = SAVE_OUTPUT_VIDEO
        self.output_path       = OUTPUT_VIDEO_PATH
        self.output_fps        = OUTPUT_VIDEO_FPS
        self.anpr_enabled      = ANPR_ENABLED
        self.no_display        = no_display

        # ★ Performance config
        self.frame_skip         = frame_skip_override or FRAME_SKIP
        self.use_threaded_reader = USE_THREADED_READER
        self.queue_maxsize      = FRAME_QUEUE_MAXSIZE
        self.capture_resize     = CAPTURE_RESIZE       # (w, h) or None
        self.display_scale      = DISPLAY_SCALE        # 0.0–1.0
        self.gc_interval        = GC_INTERVAL_FRAMES
        self.max_tracked        = MAX_TRACKED_OBJECTS
        self.pos_history_maxlen = POSITION_HISTORY_MAXLEN
        self.db_wal_mode        = DB_WAL_MODE

        # Runtime state
        self.track_zones:    dict = {}
        self.last_saved:     dict = {}
        self.prev_positions: dict = {}
        self.frame_count     = 0
        self.fps_counter     = 0
        self.fps             = 0.0
        self.paused          = False
        self.video_writer    = None
        self._fps_start      = time.time()
        self._ffmpeg_proc    = None
        self._frame_queue    = None

        # ★ ANPR async executor (max 1 thread — serial OCR)
        self._anpr_executor  = ThreadPoolExecutor(max_workers=1)
        self._anpr_futures   = {}   # track_id → Future

        # Load komponen
        self._load_model(YOLO_MODEL)
        self._load_tracker()
        self._load_db()
        self._load_anpr()
        self._load_speed_config()
        self._warmup_model()

    # ----------------------------------------------------------
    # LOAD COMPONENTS
    # ----------------------------------------------------------

    def _load_model(self, model_name: str):
        from ultralytics import YOLO
        logger.info(f"Loading YOLO model: {model_name}")
        self.model = YOLO(model_name)
        logger.info("YOLO loaded ✓")

    def _load_tracker(self):
        if ByteTrackTracker is None:
            raise RuntimeError(
                "Tracking tidak tersedia. Install `trackers` atau `supervision` package."
            )
        self.tracker = ByteTrackTracker()
        logger.info("ByteTrack loaded ✓")

    def _load_db(self):
        from database import DatabaseManager
        self.db = DatabaseManager()
        if self.db_wal_mode:
            try:
                # WAL mode: writes tidak block reads
                self.db._conn.execute("PRAGMA journal_mode=WAL")
                self.db._conn.execute("PRAGMA synchronous=NORMAL")
                logger.info("SQLite WAL mode aktif ✓")
            except Exception:
                pass
        # ★ Semua DB write via background thread
        self.async_writer = AsyncDBWriter(self.db)
        logger.info("Async DB writer started ✓")

    def _load_anpr(self):
        self.anpr = None
        if not self.anpr_enabled:
            return
        try:
            from anpr import ANPRReader
            self.anpr = ANPRReader()
            logger.info("ANPR loaded ✓")
        except ImportError:
            logger.warning("anpr.py tidak ditemukan.")
        except Exception as e:
            logger.warning(f"ANPR gagal load: {e}")

    def _load_speed_config(self):
        from config import (
            SPEED_PIXELS_PER_METER, SPEED_HISTORY_FRAMES,
            SPEED_LIMIT_KMH,
        )
        self.px_per_meter       = SPEED_PIXELS_PER_METER
        self.speed_history_n    = SPEED_HISTORY_FRAMES
        self.speed_limit_kmh    = SPEED_LIMIT_KMH
        self._seconds_per_frame = 1.0 / 25.0

    def _warmup_model(self):
        """
        ★ Warmup: jalankan inference sekali dengan dummy frame.
        Tanpa ini, frame pertama bisa lag 1-3 detik (model load ke memori).
        """
        logger.info("Model warmup...")
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        self.model(dummy, conf=self.conf, iou=self.iou,
                   imgsz=self.imgsz, verbose=False)
        logger.info("Warmup selesai ✓")

    # ----------------------------------------------------------
    # SPEED ESTIMATOR
    # ----------------------------------------------------------

    def _estimate_speed(self, track_id: int) -> float:
        hist = self.prev_positions.get(track_id)
        if not hist or len(hist) < 3:
            return 0.0

        pts = list(hist)[-self.speed_history_n:]
        if len(pts) < 2:
            return 0.0

        total_px = 0.0
        for i in range(1, len(pts)):
            dx = pts[i][0] - pts[i-1][0]
            dy = pts[i][1] - pts[i-1][1]
            total_px += (dx**2 + dy**2) ** 0.5

        n_intervals = len(pts) - 1
        elapsed_s   = n_intervals * self._seconds_per_frame * self.frame_skip
        if elapsed_s <= 0 or self.px_per_meter <= 0:
            return 0.0

        speed_kmh = (total_px / self.px_per_meter) / elapsed_s * 3.6
        return round(min(speed_kmh, 200.0), 1)

    # ----------------------------------------------------------
    # ★ MEMORY GUARD — hapus track lama
    # ----------------------------------------------------------

    def _gc_stale_tracks(self, active_ids: set):
        """
        Hapus entry dict untuk track_id yang sudah tidak aktif.
        Dipanggil setiap GC_INTERVAL_FRAMES.
        """
        # Hapus posisi history track yang hilang
        stale = [tid for tid in list(self.prev_positions.keys())
                 if tid not in active_ids]
        for tid in stale:
            del self.prev_positions[tid]
            self.track_zones.pop(tid, None)
            self.last_saved.pop(tid, None)
            self._anpr_futures.pop(tid, None)

        # ★ Jika masih terlalu banyak track, buang yang paling lama tidak aktif
        if len(self.prev_positions) > self.max_tracked:
            excess = list(self.prev_positions.keys())[
                : len(self.prev_positions) - self.max_tracked
            ]
            for tid in excess:
                self.prev_positions.pop(tid, None)
                self.track_zones.pop(tid, None)
                self.last_saved.pop(tid, None)

        # Python GC manual
        gc.collect()

    # ----------------------------------------------------------
    # THREADED FRAME READER
    # ----------------------------------------------------------

    def _start_threaded_reader(self, cap, use_pipe: bool):
        q = queue.Queue(maxsize=self.queue_maxsize)
        self._frame_queue = q

        resize_to = self.capture_resize   # (w, h) or None

        def _reader():
            while True:
                if use_pipe:
                    ret, frame = self._read_pipe_frame()
                else:
                    ret, frame = cap.read()

                if not ret:
                    q.put((False, None))
                    break

                # ★ Resize di reader thread — hemat RAM & CPU di main thread
                if resize_to and frame is not None:
                    frame = cv2.resize(frame, resize_to,
                                       interpolation=cv2.INTER_LINEAR)

                # Drop frame lama jika queue penuh
                if q.full():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
                q.put((True, frame))

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        logger.info(f"Threaded reader started (queue={self.queue_maxsize}, "
                    f"resize={resize_to}) ✓")

    def _read_threaded_frame(self):
        try:
            return self._frame_queue.get(timeout=5.0)
        except queue.Empty:
            return False, None

    # ----------------------------------------------------------
    # CAPTURE
    # ----------------------------------------------------------

    def _open_capture(self):
        src = self.source

        if not (isinstance(src, str) and ".m3u8" in src):
            cap = cv2.VideoCapture(src)
            if cap.isOpened():
                # ★ Set buffer size kecil — kurangi latency
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                logger.info(f"VideoCapture dibuka: {str(src)[:60]}")
                return cap
            cap.release()
            logger.warning("VideoCapture gagal, mencoba ffmpeg pipe...")

        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "ffmpeg tidak ditemukan.\n"
                "  Linux   : sudo apt install ffmpeg\n"
                "  Windows : winget install ffmpeg\n"
                "  Mac     : brew install ffmpeg"
            )

        self._start_ffmpeg_pipe(src)
        return None

    def _start_ffmpeg_pipe(self, url: str):
        w, h = self.capture_resize or (1280, 720)
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-re",
            "-i",       url,
            "-vf",      f"scale={w}:{h}",
            "-f",       "rawvideo",
            "-pix_fmt", "bgr24",
            "-",
        ]
        self._ffmpeg_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**8,
        )
        self._ffmpeg_w = w
        self._ffmpeg_h = h
        logger.info(f"ffmpeg pipe: {w}x{h} BGR ✓")

    def _read_pipe_frame(self):
        nbytes = self._ffmpeg_w * self._ffmpeg_h * 3
        raw    = self._ffmpeg_proc.stdout.read(nbytes)
        if len(raw) < nbytes:
            return False, None
        frame = np.frombuffer(raw, np.uint8).reshape(
            (self._ffmpeg_h, self._ffmpeg_w, 3))
        return True, frame.copy()

    # ----------------------------------------------------------
    # ★ ASYNC ANPR — tidak block main loop
    # ----------------------------------------------------------

    def _request_anpr_async(self, track_id: int, roi: np.ndarray):
        """Submit ANPR ke thread pool; hasil diambil di frame berikutnya."""
        if track_id in self._anpr_futures:
            fut = self._anpr_futures[track_id]
            if not fut.done():
                return   # masih processing, skip

        roi_copy = roi.copy()   # copy agar tidak data race
        fut = self._anpr_executor.submit(
            self.anpr.read_plate_cached, roi_copy, track_id
        )
        self._anpr_futures[track_id] = fut

    def _get_anpr_result(self, track_id: int) -> str:
        """Ambil hasil ANPR jika sudah selesai, else return None."""
        fut = self._anpr_futures.get(track_id)
        if fut and fut.done():
            try:
                return fut.result()
            except Exception:
                return None
        return None

    # ----------------------------------------------------------
    # PROCESS FRAME
    # ----------------------------------------------------------

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        import supervision as sv

        self.frame_count += 1
        now = time.time()

        # ★ Resize jika belum (fallback jika tidak pakai threaded reader)
        if self.capture_resize:
            h, w = frame.shape[:2]
            tw, th = self.capture_resize
            if (w, h) != (tw, th):
                frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_LINEAR)

        # Layer 1: Zona
        frame = draw_zones(frame, self.zones)

        # YOLOv8 inference
        results = self.model(
            frame,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            half=self.infer_half,   # ★ float16 di GPU
            verbose=False,
        )[0]

        cls_arr = results.boxes.cls.cpu().numpy().astype(int)
        mask    = np.isin(cls_arr, list(self.vehicle_classes.keys()))

        if mask.sum() == 0:
            self._draw_hud(frame)
            self._update_fps()
            # ★ GC check
            if self.frame_count % self.gc_interval == 0:
                self._gc_stale_tracks(set())
            return frame

        detections = sv.Detections(
            xyxy       = results.boxes.xyxy.cpu().numpy()[mask],
            confidence = results.boxes.conf.cpu().numpy()[mask],
            class_id   = cls_arr[mask],
        )
        detections = self.tracker.update(detections)

        active_zones: set = set()
        active_ids:   set = set()

        tracker_ids = (
            detections.tracker_id
            if detections.tracker_id is not None
            else [None] * len(detections)
        )

        for xyxy, conf_score, cls_id, track_id in zip(
            detections.xyxy, detections.confidence,
            detections.class_id, tracker_ids,
        ):
            if track_id is None:
                continue

            active_ids.add(track_id)
            x1, y1, x2, y2 = map(int, xyxy)
            hitbox          = get_bbox_bottom_center(x1, y1, x2, y2)
            vehicle_type    = self.vehicle_classes.get(int(cls_id), "car")

            # ★ History posisi dengan maxlen terbatas
            if track_id not in self.prev_positions:
                self.prev_positions[track_id] = deque(
                    maxlen=self.pos_history_maxlen)
            self.prev_positions[track_id].append(hitbox)

            # Collision detection
            for zone_name, zone_info in self.zones.items():
                in_zone = point_in_polygon(hitbox, zone_info["polygon"])
                vtype   = zone_info.get("violation_type", "zone_violation")

                if in_zone:
                    active_zones.add(zone_name)

                    if track_id not in self.track_zones:
                        self.track_zones[track_id] = {
                            "zone":       zone_name,
                            "enter_time": now,
                            "violation":  vtype,
                        }
                    else:
                        duration = now - self.track_zones[track_id]["enter_time"]

                        if vtype == "illegal_parking" and duration < self.parking_threshold:
                            continue

                        if now - self.last_saved.get(track_id, 0) < self.violation_cooldown:
                            continue

                        # ★ ANPR async — tidak blocking
                        plate = "UNKNOWN"
                        if self.anpr:
                            # Submit async jika belum
                            mid_y = y1 + (y2 - y1) // 2
                            roi   = frame[max(0, mid_y):y2, max(0, x1):x2]
                            if roi.size > 0:
                                self._request_anpr_async(int(track_id), roi)
                            # Ambil hasil sebelumnya jika ada
                            result = self._get_anpr_result(int(track_id))
                            if result:
                                plate = result

                        spd_now = self._estimate_speed(track_id)

                        # ★ DB write async — tidak blocking
                        self.async_writer.write({
                            "timestamp":        datetime.now().isoformat(),
                            "camera_id":        self.camera_id,
                            "track_id":         int(track_id),
                            "vehicle_type":     vehicle_type,
                            "license_plate":    plate,
                            "violation_type":   vtype,
                            "zone_name":        zone_name,
                            "duration_seconds": round(duration, 1),
                            "speed_kmh":        spd_now,
                            "confidence":       round(float(conf_score), 3),
                            "latitude":         self.cam_info.get("lat"),
                            "longitude":        self.cam_info.get("lon"),
                        })
                        self.last_saved[track_id] = now
                        logger.info(f"Violation: {vtype} | {plate} | {duration:.0f}s")

                else:
                    if (track_id in self.track_zones and
                            self.track_zones[track_id]["zone"] == zone_name):
                        del self.track_zones[track_id]

            # Speed & render
            speed_kmh  = self._estimate_speed(track_id)
            speed_str  = f"{speed_kmh:.0f}km/h" if speed_kmh > 1 else ""
            over_speed = speed_kmh > self.speed_limit_kmh and speed_kmh > 1

            in_violation = track_id in self.track_zones

            # Ambil cached plate dari future jika ada
            cached_plate = ""
            if self.anpr:
                result = self._get_anpr_result(int(track_id))
                if result and result != "UNKNOWN":
                    cached_plate = f" [{result}]"

            if in_violation:
                vt     = self.track_zones[track_id]["violation"]
                dur    = now - self.track_zones[track_id]["enter_time"]
                spd_tag = f" {speed_str}" if speed_str else ""
                label   = f"#{track_id} {vt[:10]}{spd_tag} {dur:.0f}s{cached_plate}"
                draw_violation_box(frame, (x1, y1, x2, y2), label, vt, dur)
                draw_direction_arrow(frame, track_id, hitbox,
                                     self.prev_positions, get_violation_color(vt))
            else:
                spd_tag   = f" {speed_str}" if speed_str else ""
                box_color = (0, 80, 255) if over_speed else (0, 220, 0)
                label     = f"#{track_id} {vehicle_type}{spd_tag}{cached_plate}"
                draw_bbox_label(frame, (x1, y1, x2, y2), label, box_color)
                draw_proximity_warning(frame, hitbox, self.zones)

            draw_hitbox(frame, hitbox, in_violation or over_speed)

        # Highlight zona aktif
        for zname in active_zones:
            draw_zone_active_highlight(frame, self.zones[zname]["polygon"])

        # HUD
        self._draw_hud(frame)
        self._update_fps()

        # ★ GC setiap N frame
        if self.frame_count % self.gc_interval == 0:
            self._gc_stale_tracks(active_ids)

        return frame

    # ----------------------------------------------------------
    # HUD
    # ----------------------------------------------------------

    def _draw_hud(self, frame: np.ndarray):
        h, w   = frame.shape[:2]
        hud_w  = 370
        hud_h  = 115

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (hud_w, hud_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        cv2.rectangle(frame, (0, 0), (hud_w, hud_h), (0, 180, 180), 1)

        skip_tag = f"  skip:{self.frame_skip}" if self.frame_skip > 1 else ""
        lines = [
            f"DISHUB DKI  |  {self.camera_id}",
            f"FPS: {self.fps:.1f}  |  Frame: {self.frame_count}{skip_tag}",
            f"Tracks: {len(self.prev_positions)}  |  Violations: {len(self.track_zones)}  |  Limit: {self.speed_limit_kmh}km/h",
            datetime.now().strftime("%d/%m/%Y  %H:%M:%S"),
        ]
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (8, 22 + i*22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                        (0, 255, 255), 1, cv2.LINE_AA)

        hint = "Q: Quit   S: Screenshot   P: Pause/Resume"
        (hw, _), _ = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.rectangle(frame, (0, h-22), (hw+12, h), (0, 0, 0), -1)
        cv2.putText(frame, hint, (6, h-7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

    def _update_fps(self):
        self.fps_counter += 1
        elapsed = time.time() - self._fps_start
        if elapsed >= 1.0:
            self.fps = self.fps_counter / elapsed
            if self.fps > 0:
                self._seconds_per_frame = 1.0 / self.fps
            self.fps_counter = 0
            self._fps_start  = time.time()

    # ----------------------------------------------------------
    # SCREENSHOT
    # ----------------------------------------------------------

    def _save_screenshot(self, frame: np.ndarray):
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"screenshot_{ts}.jpg"
        cv2.imwrite(path, frame)
        print(f"Screenshot disimpan: {path}")

    # ----------------------------------------------------------
    # RUN
    # ----------------------------------------------------------

    def run(self):
        try:
            cap = self._open_capture()
        except RuntimeError as e:
            print(f"ERROR: {e}")
            return

        use_pipe = (cap is None)

        # Video writer
        if self.save_video:
            fw, fh = self.capture_resize or (1280, 720)
            if not use_pipe and cap:
                fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(
                self.output_path, fourcc, self.output_fps, (fw, fh))

        # Threaded reader
        is_stream = use_pipe or (isinstance(self.source, str) and
                                  ("rtsp://" in self.source or ".m3u8" in self.source))
        if self.use_threaded_reader and is_stream:
            self._start_threaded_reader(cap, use_pipe)
            use_thread = True
        else:
            use_thread = False

        src_short = (str(self.source)[:70] + "...") if len(str(self.source)) > 70 else str(self.source)
        print(f"\n{'='*60}")
        print(f"  DISHUB DKI — Traffic Enforcement System")
        print(f"  Source    : {src_short}")
        print(f"  Model     : {self.imgsz}px | skip:{self.frame_skip} | half:{self.infer_half}")
        print(f"  Display   : {'HEADLESS (no window)' if self.no_display else f'scale={self.display_scale}'}")
        print(f"  ANPR      : {'ON' if self.anpr_enabled else 'OFF'}")
        print(f"{'='*60}\n")
        print("Kontrol: Q=Quit  S=Screenshot  P=Pause")

        last_annotated = None
        read_counter   = 0

        try:
            while True:
                if not self.paused:
                    if use_thread:
                        ret, frame = self._read_threaded_frame()
                    elif use_pipe:
                        ret, frame = self._read_pipe_frame()
                    else:
                        ret, frame = cap.read()
                        # ★ Resize jika tidak pakai threaded reader
                        if ret and frame is not None and self.capture_resize:
                            frame = cv2.resize(frame, self.capture_resize,
                                               interpolation=cv2.INTER_LINEAR)

                    if not ret:
                        logger.info("End of stream.")
                        break

                    read_counter += 1

                    # Frame skip
                    if read_counter % self.frame_skip == 0 or last_annotated is None:
                        last_annotated = self.process_frame(frame.copy())

                    annotated = last_annotated

                else:
                    if last_annotated is not None:
                        annotated = last_annotated.copy()
                    else:
                        annotated = np.zeros((720, 1280, 3), np.uint8)
                    cv2.putText(annotated, "PAUSED", (20, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)

                if self.video_writer:
                    self.video_writer.write(annotated)

                # ★ Display — skip jika headless
                if not self.no_display:
                    if self.display_scale != 1.0 and annotated is not None:
                        h, w = annotated.shape[:2]
                        dw = int(w * self.display_scale)
                        dh = int(h * self.display_scale)
                        display_frame = cv2.resize(annotated, (dw, dh),
                                                   interpolation=cv2.INTER_LINEAR)
                    else:
                        display_frame = annotated

                    cv2.imshow("DISHUB DKI — Traffic Enforcement", display_frame)

                # ★ Non-blocking key read
                key = cv2.waitKey(1) & 0xFF
                if   key in (ord("q"), ord("Q")):
                    print("Dihentikan.")
                    break
                elif key in (ord("s"), ord("S")):
                    self._save_screenshot(annotated)
                elif key in (ord("p"), ord("P")):
                    self.paused = not self.paused
                    print("PAUSED" if self.paused else "RESUMED")

        except KeyboardInterrupt:
            print("\nDihentikan (Ctrl+C).")
        finally:
            self._anpr_executor.shutdown(wait=False)
            if cap:
                cap.release()
            if self._ffmpeg_proc:
                self._ffmpeg_proc.terminate()
                self._ffmpeg_proc.wait()
            if self.video_writer:
                self.video_writer.release()
            if not self.no_display:
                cv2.destroyAllWindows()
            print(f"\nSesi selesai — Frame: {self.frame_count}  |  FPS rata-rata: {self.fps:.1f}")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="DISHUB DKI — Traffic Violation Detector (Optimized)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--source", type=str, default=None,
        help=(
            "Sumber video:\n"
            "  (kosong)              → webcam default\n"
            "  0 / 1 / 2            → webcam index\n"
            "  video.mp4            → file video\n"
            "  rtsp://...           → RTSP / IP Camera\n"
            "  https://youtu.be/... → YouTube live/video\n"
        ),
    )
    parser.add_argument(
        "--no-display", action="store_true",
        help="Headless mode — tidak buka window (untuk server/cloud/SSH)",
    )
    parser.add_argument(
        "--frame-skip", type=int, default=None,
        help="Override FRAME_SKIP dari config (misal: --frame-skip 5)",
    )
    args = parser.parse_args()

    # Cek dependency
    deps = _check_imports()
    if not all(deps.values()):
        missing = [k for k, v in deps.items() if not v]
        print(f"ERROR dependency kurang: {', '.join(missing)}")
        print("  Jalankan: pip install ultralytics supervision trackers")
        sys.exit(1)

    # Resolve source
    raw = args.source
    if raw is None:
        source = 0
    elif raw.isdigit():
        source = int(raw)
    elif is_youtube_url(raw):
        try:
            source = get_youtube_stream_url(raw)
        except RuntimeError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        source = raw

    system = TrafficEnforcementSystem(
        source=source,
        no_display=args.no_display,
        frame_skip_override=args.frame_skip,
    )
    system.run()
