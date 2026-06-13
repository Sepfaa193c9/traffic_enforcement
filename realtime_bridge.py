# realtime_bridge.py
# Bridge untuk real-time monitoring di Streamlit Dashboard
# Menghubungkan detector.py + YOLO tracking + YouTube streaming

import logging
import threading
import time
import queue
from datetime import datetime
from typing import Optional, Dict, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# YOUTUBE URL RESOLVER
# ============================================================

def resolve_youtube_url(youtube_url: str) -> str:
    """
    Resolve YouTube live/video URL ke direct stream URL.
    
    Args:
        youtube_url: URL YouTube (live atau video)
    
    Returns:
        Direct stream URL yang bisa dibuka OpenCV
    
    Raises:
        RuntimeError: Jika tidak bisa resolve
    """
    import subprocess
    import shutil
    
    # Cek yt-dlp tersedia
    if not shutil.which("yt-dlp"):
        raise RuntimeError(
            "yt-dlp tidak ditemukan.\n"
            "  Install: pip install yt-dlp\n"
            "  atau: pip install -r requirements.txt"
        )
    
    fmt = "best[height<=720][ext=mp4]/best[height<=720]/best"
    cmd = [
        "yt-dlp", "-g",
        "-f", fmt,
        "--no-warnings",
        "--no-playlist",
        "--no-live-from-start",  # Mulai dari live edge, bukan awal
        youtube_url,
    ]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timeout. Cek koneksi internet.")
    
    if res.returncode != 0:
        err = res.stderr.decode(errors="ignore").strip()
        raise RuntimeError(f"yt-dlp gagal: {err or res.stdout}")
    
    urls = [u.strip() for u in res.stdout.strip().splitlines() if u.strip()]
    if not urls:
        raise RuntimeError("yt-dlp tidak mengembalikan URL.")
    
    logger.info(f"[YouTube] URL resolved: {urls[0][:80]}...")
    return urls[0]


# ============================================================
# STREAMLIT REAL-TIME DETECTOR BRIDGE
# ============================================================

class RealtimeDetectorBridge:
    """
    Bridge untuk menjalankan detector YOLO di background thread.
    
    Streamlit dapat polling frame terbaru tanpa blocking.
    Thread-safe dengan lock.
    
    Features:
    - Multi-source (webcam, RTSP, YouTube, file)
    - YOLO tracking dengan ByteTrack (ID konsisten)
    - Auto-reconnect pada network error
    - Async ANPR (plat nomor) - optional
    """
    
    _MAX_RECONNECT = 3
    _FRAME_TIMEOUT = 30.0
    _STARTUP_TIMEOUT = 60.0
    
    def __init__(self, confidence: float = 0.35):
        self.confidence = confidence
        
        # Frame & stats storage
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_stats: Dict = {}
        self.latest_detections: Dict = {}  # Track info untuk export
        
        # Thread control
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.is_running = False
        self.error: Optional[str] = None
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Metrics
        self.frame_count = 0
        self.fps = 0.0
        self._last_fps_update = time.time()
        self._frame_since_fps = 0
    
    def start(self, source: str):
        """
        Mulai detector background thread.
        
        Args:
            source: Video source (0, 'video.mp4', 'rtsp://...', 'https://youtu.be/...')
        """
        if self._thread and self._thread.is_alive():
            logger.warning("[Bridge] Detector sudah jalan, skip start()")
            return
        
        self._stop_event.clear()
        self.error = None
        self.latest_frame = None
        self.latest_stats = {}
        self.latest_detections = {}
        self.is_running = True
        
        self._thread = threading.Thread(
            target=self._run_detector,
            args=(source,),
            daemon=True
        )
        self._thread.start()
        logger.info("[Bridge] Detector thread started")
    
    def stop(self):
        """Hentikan detector background thread."""
        self._stop_event.set()
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("[Bridge] Detector thread stopped")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Ambil frame terbaru (thread-safe)."""
        with self._lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()
    
    def get_latest_stats(self) -> Dict:
        """Ambil stats deteksi terbaru (thread-safe)."""
        with self._lock:
            return self.latest_stats.copy()
    
    def get_latest_detections(self) -> Dict:
        """Ambil info deteksi detailed (track ID, plat, dll)."""
        with self._lock:
            return self.latest_detections.copy()
    
    # ----------------------------------------------------------
    # DETECTOR LOOP (jalan di background thread)
    # ----------------------------------------------------------
    
    def _run_detector(self, source: str):
        """Main detector loop - jalan di background thread."""
        try:
            from ultralytics import YOLO
            
            # ── 1. Resolve source ───────────────────────────
            stream_url = self._resolve_source(source)
            
            # ── 2. Load YOLO model ─────────────────────────
            logger.info("[Bridge] Loading YOLO model...")
            model = YOLO("yolov8n.pt")
            
            # Warmup
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            model(dummy, conf=self.confidence, verbose=False)
            logger.info("[Bridge] YOLO model loaded ✓")
            
            # ── 3. Main loop with auto-reconnect ───────────
            reconnect_count = 0
            
            while not self._stop_event.is_set():
                
                # Buka capture
                cap = self._open_capture(stream_url)
                if not cap or not cap.isOpened():
                    reconnect_count += 1
                    if reconnect_count > self._MAX_RECONNECT:
                        self.error = "Stream tidak bisa terbuka setelah beberapa percobaan"
                        break
                    
                    logger.warning(f"[Bridge] Retry {reconnect_count}/{self._MAX_RECONNECT}...")
                    time.sleep(3)
                    try:
                        stream_url = self._resolve_source(source)
                    except Exception as e:
                        self.error = str(e)
                        break
                    continue
                
                reconnect_count = 0
                
                # ── 4. Frame read loop ─────────────────────
                startup_deadline = time.time() + self._STARTUP_TIMEOUT
                last_frame_time = time.time()
                got_first_frame = False
                
                while not self._stop_event.is_set():
                    
                    # Startup timeout
                    if not got_first_frame and time.time() > startup_deadline:
                        logger.warning("[Bridge] Startup timeout")
                        break
                    
                    # Frame timeout
                    if got_first_frame and (time.time() - last_frame_time) > self._FRAME_TIMEOUT:
                        logger.warning("[Bridge] Frame timeout, reconnect...")
                        break
                    
                    # ★ FIX: Buang frame lama di buffer
                    for _ in range(4):
                        cap.grab()
                    
                    ret, frame = cap.retrieve()
                    if not ret or frame is None:
                        logger.warning("[Bridge] cap.retrieve() failed")
                        break
                    
                    last_frame_time = time.time()
                    got_first_frame = True
                    
                    # ── 5. YOLO Detection + Tracking ────────
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    try:
                        # Gunakan model.track() agar tracking ID konsisten
                        results = model.track(
                            frame_rgb,
                            conf=self.confidence,
                            persist=True,
                            tracker="bytetrack.yaml",
                            verbose=False,
                        )[0]
                        
                        annotated = results.plot()
                        
                        # ── 6. Extract stats ────────────────
                        stats = self._extract_stats(results, model)
                        detections = self._extract_detections(results, model)
                        
                        # ── 7. Update shared state (thread-safe)
                        with self._lock:
                            self.latest_frame = annotated
                            self.latest_stats = stats
                            self.latest_detections = detections
                            self.frame_count += 1
                        
                        self._update_fps()
                    
                    except Exception as e:
                        logger.error(f"[Bridge] Processing error: {e}")
                        self.error = f"Processing error: {str(e)[:100]}"
                        break
                
                cap.release()
                
                if self._stop_event.is_set():
                    break
                
                # Reconnect
                reconnect_count += 1
                if reconnect_count > self._MAX_RECONNECT:
                    self.error = "Stream terputus berkali-kali"
                    break
                
                logger.info(f"[Bridge] Reconnecting {reconnect_count}/{self._MAX_RECONNECT}...")
                time.sleep(2)
        
        except Exception as e:
            self.error = str(e)
            logger.error(f"[Bridge] Fatal error: {e}", exc_info=True)
        
        finally:
            self.is_running = False
    
    def _resolve_source(self, source: str) -> str:
        """Resolve source (YouTube → direct URL, or passthrough)."""
        if isinstance(source, int):
            return source  # Webcam index
        
        if isinstance(source, str):
            if any(x in source for x in ("youtube.com", "youtu.be")):
                logger.info("[Bridge] Resolving YouTube URL...")
                return resolve_youtube_url(source)
        
        return source  # File, RTSP, dll
    
    def _open_capture(self, source) -> Optional[cv2.VideoCapture]:
        """Buka VideoCapture dengan optimasi untuk streaming."""
        try:
            if isinstance(source, str):
                cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            else:
                cap = cv2.VideoCapture(source)
            
            if not cap.isOpened():
                return None
            
            # Minimize buffer
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Seek ke live edge jika ada
            total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if total and total > 100:
                target = int(total * 0.95)
                cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            
            return cap
        
        except Exception as e:
            logger.error(f"[Bridge] Open capture failed: {e}")
            return None
    
    def _extract_stats(self, results, model: "YOLO") -> Dict:
        """Extract detection statistics dari YOLO results."""
        from collections import Counter
        
        # Class names
        vehicle_keys = {"car", "motorcycle", "bus", "truck", "bicycle"}
        
        # Count classes
        cls_list = []
        if results.boxes is not None and len(results.boxes) > 0:
            cls_list = [model.names[int(c)] for c in results.boxes.cls.cpu().tolist()]
        
        cnt = Counter(cls_list)
        vehicles = {k: v for k, v in cnt.items() if k in vehicle_keys}
        others = sum(v for k, v in cnt.items() if k not in vehicle_keys)
        
        # Track count
        track_count = 0
        if hasattr(results, "boxes") and results.boxes is not None:
            if hasattr(results.boxes, "id") and results.boxes.id is not None:
                track_count = len(set(results.boxes.id.cpu().tolist()))
        
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "total": len(results.boxes) if results.boxes is not None else 0,
            "tracked": track_count,
            "vehicles": vehicles,
            "others": others,
            "fps": round(self.fps, 1),
            "frame_count": self.frame_count,
        }
    
    def _extract_detections(self, results, model: "YOLO") -> Dict:
        """Extract detailed detection info (untuk export/analysis)."""
        detections = []
        
        if results.boxes is None or len(results.boxes) == 0:
            return {"count": 0, "objects": []}
        
        for i, (xyxy, conf, cls_id) in enumerate(zip(
            results.boxes.xyxy.cpu().numpy(),
            results.boxes.conf.cpu().numpy(),
            results.boxes.cls.cpu().numpy(),
        )):
            x1, y1, x2, y2 = map(int, xyxy)
            
            track_id = None
            if hasattr(results.boxes, "id") and results.boxes.id is not None:
                track_id = int(results.boxes.id[i].cpu().item())
            
            detections.append({
                "bbox": [x1, y1, x2, y2],
                "class": model.names[int(cls_id)],
                "confidence": float(conf),
                "track_id": track_id,
            })
        
        return {
            "count": len(detections),
            "objects": detections,
        }
    
    def _update_fps(self):
        """Update FPS counter."""
        now = time.time()
        self._frame_since_fps += 1
        
        elapsed = now - self._last_fps_update
        if elapsed >= 1.0:
            self.fps = self._frame_since_fps / elapsed
            self._frame_since_fps = 0
            self._last_fps_update = now


# ============================================================
# SINGLETON PATTERN (untuk Streamlit caching)
# ============================================================

_bridge_instance: Optional[RealtimeDetectorBridge] = None

def get_detector_bridge(confidence: float = 0.35) -> RealtimeDetectorBridge:
    """Get singleton instance dari bridge."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = RealtimeDetectorBridge(confidence=confidence)
    return _bridge_instance
