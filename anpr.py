# ============================================================
# anpr.py — Automatic Number Plate Recognition (ANPR)
# DISHUB DKI Jakarta | AI Open Innovation Challenge 2026
# ============================================================
"""
Baca plat nomor kendaraan dari crop gambar menggunakan EasyOCR.

Usage:
    from anpr import ANPRReader

    anpr = ANPRReader()
    plate = anpr.read_plate(roi_image)   # roi = numpy array crop kendaraan
    print(plate)  # "B 1234 ABC"
"""

import logging
import re

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# FORMAT PLAT NOMOR INDONESIA
# ============================================================
# Format umum: [huruf 1-2] [angka 1-4] [huruf 1-3]
# Contoh: B 1234 ABC, D 5678 XY, BL 999 Z
PLATE_PATTERN = re.compile(
    r"\b([A-Z]{1,2})\s*(\d{1,4})\s*([A-Z]{1,3})\b"
)

# Koreksi karakter OCR yang sering salah baca
OCR_CORRECTIONS = {
    "0": "O", "1": "I", "5": "S", "8": "B",   # angka → huruf (di bagian huruf)
    "O": "0", "I": "1", "S": "5", "B": "8",   # huruf → angka (di bagian angka)
    "D": "0", "G": "6", "Z": "2",
}


# ============================================================
# ANPR READER
# ============================================================

class ANPRReader:
    """
    Wrapper EasyOCR untuk membaca plat nomor kendaraan Indonesia.

    Args:
        languages: List kode bahasa EasyOCR (default: ['id', 'en']).
        gpu:       Gunakan GPU jika tersedia (default: False).
        min_confidence: Minimum confidence untuk menerima hasil (default: 0.4).
    """

    def __init__(
        self,
        languages: list[str] = None,
        gpu: bool = False,
        min_confidence: float = 0.4,
    ):
        from config import (
            ANPR_LANGUAGES, ANPR_GPU, ANPR_CONFIDENCE_THRESHOLD,
            ANPR_THROTTLE_SECONDS, ANPR_CACHE_ENABLED,
        )

        self.languages          = languages or ANPR_LANGUAGES
        self.gpu                = gpu or ANPR_GPU
        self.min_confidence     = min_confidence or ANPR_CONFIDENCE_THRESHOLD
        self.throttle_seconds   = ANPR_THROTTLE_SECONDS
        self.cache_enabled      = ANPR_CACHE_ENABLED
        self.reader             = None

        # Cache: track_id → {"plate": str, "last_read": float}
        self._plate_cache: dict = {}

        self._load_reader()

    def _load_reader(self):
        try:
            import easyocr
            logger.info("Loading EasyOCR model (pertama kali ~200MB)...")
            self.reader = easyocr.Reader(self.languages, gpu=self.gpu)
            logger.info("EasyOCR loaded ✓")
        except ImportError:
            logger.error("EasyOCR tidak tersedia. Jalankan: pip install easyocr")
        except Exception as e:
            logger.error(f"Gagal load EasyOCR: {e}")

    # ----------------------------------------------------------
    # PREPROCESSING
    # ----------------------------------------------------------

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocessing gambar sebelum OCR untuk meningkatkan akurasi.

        Pipeline:
        1. Resize agar plat cukup besar (min 120px lebar)
        2. Grayscale
        3. CLAHE (contrast enhancement)
        4. Gaussian blur ringan
        5. Adaptive thresholding
        """
        if image is None or image.size == 0:
            return image

        # Resize jika terlalu kecil
        h, w = image.shape[:2]
        if w < 120:
            scale = 120 / w
            image = cv2.resize(image, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_CUBIC)

        # Grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        gray  = clahe.apply(gray)

        # Denoise
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Morfologi: hilangkan noise kecil (titik-titik) dan perkuat karakter
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        return thresh

    # ----------------------------------------------------------
    # POST-PROCESS TEKS
    # ----------------------------------------------------------

    def _clean_text(self, text: str) -> str:
        """Bersihkan dan normalisasi teks hasil OCR."""
        # Uppercase & hapus karakter non-alphanumeric
        text = re.sub(r"[^A-Z0-9\s]", "", text.upper())
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _correct_plate(self, text: str) -> str:
        """
        Coba perbaiki teks menjadi format plat nomor Indonesia.
        Kembalikan teks asli jika tidak cocok pola.
        """
        match = PLATE_PATTERN.search(text)
        if match:
            prefix  = match.group(1)
            numbers = match.group(2)
            suffix  = match.group(3)
            return f"{prefix} {numbers} {suffix}"
        return text

    # ----------------------------------------------------------
    # READ PLATE
    # ----------------------------------------------------------

    def read_plate(self, image: np.ndarray) -> str:
        """
        Baca plat nomor dari crop gambar kendaraan.

        Args:
            image: Numpy array BGR (crop area kendaraan).

        Returns:
            String plat nomor (contoh: "B 1234 ABC") atau "UNKNOWN".
        """
        if self.reader is None:
            return "UNKNOWN"

        if image is None or image.size == 0:
            return "UNKNOWN"

        # Coba deteksi area plat terlebih dahulu
        plate_roi = self._detect_plate_region(image)
        if plate_roi is not None:
            image = plate_roi

        # Preprocessing
        processed = self.preprocess(image)

        try:
            results = self.reader.readtext(processed, detail=1)
        except Exception as e:
            logger.debug(f"OCR error: {e}")
            return "UNKNOWN"

        if not results:
            return "UNKNOWN"

        # Gabungkan semua teks dengan confidence cukup
        texts = [
            self._clean_text(text)
            for _, text, conf in results
            if conf >= self.min_confidence and text.strip()
        ]

        if not texts:
            return "UNKNOWN"

        combined = " ".join(texts)
        plate    = self._correct_plate(combined)

        logger.debug(f"ANPR raw: {combined!r} → {plate!r}")
        return plate if plate else "UNKNOWN"

    # ----------------------------------------------------------
    # DETEKSI AREA PLAT (OPSIONAL)
    # ----------------------------------------------------------

    def _detect_plate_region(self, image: np.ndarray) -> np.ndarray | None:
        """
        Isolasi area plat dari crop kendaraan.

        Strategi 2-langkah:
        1. Crop 40% bawah frame (plat selalu di area bawah kendaraan)
        2. Edge detection + contour filtering untuk isolasi rectangle plat

        Returns None jika tidak berhasil (fallback ke full crop).
        """
        h, w = image.shape[:2]
        # Fokus ke 40% bawah — area plat kendaraan Indonesia
        bottom_crop = image[int(h * 0.55):h, :]
        if bottom_crop.size == 0:
            return None
        image = bottom_crop
        try:
            gray  = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            blur  = cv2.bilateralFilter(gray, 9, 75, 75)
            edges = cv2.Canny(blur, 50, 200)

            contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            contours    = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

            h, w = image.shape[:2]
            for cnt in contours:
                peri   = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

                if len(approx) == 4:
                    x, y, cw, ch = cv2.boundingRect(cnt)
                    aspect = cw / ch if ch > 0 else 0

                    # Plat Indonesia umumnya aspect ratio 2.5–5.0
                    if 2.0 <= aspect <= 6.0 and cw > 60 and ch > 15:
                        roi = image[y:y+ch, x:x+cw]
                        return roi
        except Exception:
            pass

        return None

    # ----------------------------------------------------------
    # THROTTLED + CACHED READ
    # ----------------------------------------------------------

    def read_plate_cached(self, image, track_id: int) -> str:
        """
        Baca plat dengan throttle & cache per track_id.

        - Jika track_id sudah punya cache yang masih valid (< throttle_seconds),
          kembalikan cache langsung tanpa re-OCR.
        - Jika cache expired atau belum ada, jalankan OCR dan simpan hasilnya.

        Ini penting untuk livestream di mana CPU terbatas — ANPR mahal.

        Args:
            image:    Crop BGR kendaraan.
            track_id: ByteTrack ID unik kendaraan.

        Returns:
            String plat (contoh "B 1234 ABC") atau "UNKNOWN".
        """
        import time
        now = time.time()

        if self.cache_enabled and track_id in self._plate_cache:
            entry = self._plate_cache[track_id]
            # Kembalikan cache jika masih dalam throttle window
            if now - entry["last_read"] < self.throttle_seconds:
                return entry["plate"]
            # Cache ada tapi expired — re-read hanya jika plate masih UNKNOWN
            if entry["plate"] != "UNKNOWN":
                return entry["plate"]   # sudah dapat plat valid, tidak perlu re-read

        plate = self.read_plate(image)
        self._plate_cache[track_id] = {"plate": plate, "last_read": now}
        return plate

    def clear_cache(self, track_id: int = None):
        """Hapus cache satu track_id, atau semua jika track_id=None."""
        if track_id is None:
            self._plate_cache.clear()
        elif track_id in self._plate_cache:
            del self._plate_cache[track_id]

    # ----------------------------------------------------------
    # BATCH READ
    # ----------------------------------------------------------

    def read_batch(self, images: list[np.ndarray]) -> list[str]:
        """Baca banyak plat sekaligus."""
        return [self.read_plate(img) for img in images]


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🔤 ANPR Reader — Test Mode")
    print("=" * 40)

    anpr = ANPRReader()

    if len(sys.argv) > 1:
        # Test dari file gambar
        img_path = sys.argv[1]
        img = cv2.imread(img_path)
        if img is None:
            print(f"❌ Tidak bisa membuka gambar: {img_path}")
            sys.exit(1)

        plate = anpr.read_plate(img)
        print(f"Gambar  : {img_path}")
        print(f"Hasil   : {plate}")

    else:
        # Test dari webcam (ambil 1 frame)
        print("Membuka webcam untuk 1 frame test...")
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret:
                plate = anpr.read_plate(frame)
                print(f"Frame webcam → Plat: {plate}")
                cv2.imwrite("anpr_test_frame.jpg", frame)
                print("Frame disimpan: anpr_test_frame.jpg")
        else:
            print("Webcam tidak tersedia. Gunakan: python anpr.py gambar.jpg")
