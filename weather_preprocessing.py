# weather_preprocessing.py
# Modul preprocessing untuk kondisi malam, hujan, embun, dan cuaca buruk
# Terintegrasi dengan detector.py dan config.py

import cv2
import numpy as np
import logging
from skimage import exposure, restoration

logger = logging.getLogger(__name__)

# ============================================================
# KONFIGURASI (bisa di-override dari config.py)
# ============================================================

WEATHER_CONFIG = {
    'night_gamma': 1.2,
    'clahe_clip_limit': 3.0,
    'clahe_tile_size': (8, 8),
    'dehaze_strength': 0.95,
    'denoise_strength': 5,
    'brightness_threshold': 80,
    'haze_threshold': 0.6,
}


class WeatherPreprocessor:
    """
    Preprocessing adaptif untuk:
    - Malam hari (low light) → gamma correction + CLAHE
    - Hujan/Kabut → dehazing
    - Embun → contrast enhancement
    - Berbagai angle CCTV
    """
    
    def __init__(self, config: dict = None):
        self.config = config or WEATHER_CONFIG
        self._last_condition = 'day'
        
    def process(self, image: np.ndarray, condition: str = 'auto') -> np.ndarray:
        """
        Main preprocessing pipeline
        
        Args:
            image: numpy array (BGR)
            condition: 'day', 'night', 'rain', 'fog', 'dawn', 'dusk', 'auto'
        
        Returns:
            processed_image: numpy array
        """
        if image is None or image.size == 0:
            return image
            
        original_dtype = image.dtype
        if original_dtype != np.uint8:
            image = image.astype(np.uint8)
        
        # Deteksi kondisi otomatis
        if condition == 'auto':
            condition = self.detect_condition(image)
            self._last_condition = condition
        
        logger.debug(f"Processing with condition: {condition}")
        
        # Pipeline preprocessing sesuai kondisi
        if condition == 'night':
            image = self._enhance_night(image)
        elif condition in ['rain', 'fog', 'haze']:
            image = self._dehaze(image)
        elif condition in ['dawn', 'dusk', 'low_light']:
            image = self._enhance_low_light(image)
        
        # Always enhance contrast (untuk plat nomor)
        image = self._enhance_contrast(image)
        
        # Sharpening ringan
        image = self._sharpen(image)
        
        return image
    
    def detect_condition(self, image: np.ndarray) -> str:
        """
        Deteksi kondisi cuaca/cahaya dari gambar
        Returns: 'day', 'night', 'fog', 'dawn'
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Mean brightness (0-255)
        brightness = np.mean(gray)
        
        # Contrast (std dev)
        contrast = np.std(gray)
        
        # Haze detection using dark channel
        dark_channel = np.min(image, axis=2)
        haze_density = np.mean(dark_channel) / 255
        
        if brightness < self.config['brightness_threshold']:
            return 'night'
        elif haze_density > self.config['haze_threshold'] and contrast < 40:
            return 'fog'
        elif brightness < 110:
            return 'dawn'
        else:
            return 'day'
    
    def _enhance_night(self, image: np.ndarray) -> np.ndarray:
        """Enhance malam hari: gamma correction + CLAHE + denoise"""
        # Gamma correction (brighten)
        gamma = self.config['night_gamma']
        gamma_inv = 1.0 / gamma
        table = np.array([((i / 255.0) ** gamma_inv) * 255 
                          for i in range(256)]).astype(np.uint8)
        image = cv2.LUT(image, table)
        
        # CLAHE untuk detail
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(
            clipLimit=self.config['clahe_clip_limit'],
            tileGridSize=self.config['clahe_tile_size']
        )
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        image = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        # Denoise
        image = cv2.fastNlMeansDenoisingColored(
            image, None, 
            self.config['denoise_strength'], 
            self.config['denoise_strength'], 
            7, 21
        )
        
        return image
    
    def _enhance_low_light(self, image: np.ndarray) -> np.ndarray:
        """Enhance low light (dawn/dusk) - lebih ringan dari night"""
        # Boost brightness sedikit
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        v = cv2.addWeighted(v, 1.2, np.zeros_like(v), 0, 20)
        s = cv2.addWeighted(s, 1.05, np.zeros_like(s), 0, 5)
        hsv = cv2.merge([h, s, v])
        image = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        
        # CLAHE ringan
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    def _dehaze(self, image: np.ndarray) -> np.ndarray:
        """
        Dehazing untuk hujan/kabut
        Menggunakan dark channel prior sederhana
        """
        try:
            image_float = image.astype(np.float32) / 255.0
            
            # Dark channel
            dark_channel = np.min(image_float, axis=2)
            
            # Estimate atmospheric light (top 0.1% brightest)
            flat = dark_channel.flatten()
            flat.sort()
            airlight = flat[int(0.999 * len(flat))]
            
            # Transmission map
            transmission = 1 - self.config['dehaze_strength'] * (dark_channel / (airlight + 1e-6))
            transmission = np.clip(transmission, 0.15, 1)
            
            # Recover image
            recovered = np.zeros_like(image_float)
            for i in range(3):
                recovered[:, :, i] = (image_float[:, :, i] - airlight) / transmission + airlight
            
            recovered = np.clip(recovered, 0, 1) * 255
            return recovered.astype(np.uint8)
            
        except Exception as e:
            logger.warning(f"Dehaze failed: {e}")
            return self._enhance_contrast(image)
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """Enhance contrast khusus untuk plat nomor"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_eq = clahe.apply(gray)
        
        # Convert back
        if len(image.shape) == 3:
            result = cv2.cvtColor(gray_eq, cv2.COLOR_GRAY2BGR)
        else:
            result = gray_eq
            
        return result
    
    def _sharpen(self, image: np.ndarray) -> np.ndarray:
        """Sharpening ringan"""
        kernel = np.array([[-0.5, -0.5, -0.5],
                           [-0.5,  5,   -0.5],
                           [-0.5, -0.5, -0.5]])
        return cv2.filter2D(image, -1, kernel)
    
    def preprocess_for_plate(self, image: np.ndarray, condition: str = 'auto') -> np.ndarray:
        """
        Preprocessing khusus untuk plat nomor sebelum OCR
        Returns binary image siap OCR
        """
        if image is None or image.size == 0:
            return None
        
        # Resize agar cukup besar
        h, w = image.shape[:2]
        if w < 120:
            scale = 160 / w
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        
        # Process
        processed = self.process(image, condition)
        
        # Convert to grayscale
        if len(processed.shape) == 3:
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        else:
            gray = processed
        
        # Adaptive threshold
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Morphological cleaning
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        return binary
    
    def get_last_condition(self) -> str:
        return self._last_condition


# Singleton untuk dipanggil dari detector.py
_weather_preprocessor = None

def get_weather_preprocessor() -> WeatherPreprocessor:
    global _weather_preprocessor
    if _weather_preprocessor is None:
        _weather_preprocessor = WeatherPreprocessor()
    return _weather_preprocessor