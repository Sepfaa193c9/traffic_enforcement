# zone_configurator.py - Tool Interaktif Konfigurasi Zona Deteksi
# Jalankan: python zone_configurator.py --source video.mp4
# Atau: python zone_configurator.py (untuk webcam)

import cv2
import numpy as np
import argparse
from pathlib import Path

class ZoneConfigurator:
    """Tool interaktif untuk menggambar zona deteksi pada video"""

    def __init__(self, video_source=0):
        self.video_source = video_source

        # Resolve YouTube URL → direct stream URL
        if isinstance(video_source, str) and any(
            d in video_source for d in ("youtube.com", "youtu.be")
        ):
            video_source = self._resolve_youtube(video_source)
            self.video_source = video_source

        self.cap = cv2.VideoCapture(video_source)

        if not self.cap.isOpened():
            print(f"[ERROR] Tidak bisa buka source: {video_source}")
            exit(1)

        self.fps = int(self.cap.get(cv2.CAP_PROP_FPS)) or 30
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.frame = None
        self.drawing = False
        self.points = []
        self.zones = {}

        self.display_scale = 1.0
        self.display_width = self.width
        self.display_height = self.height
        self.max_display_width = 1280
        self.max_display_height = 720

        print(f"[*] Video: {self.width}x{self.height} @ {self.fps} FPS")
        print("[*] Petunjuk:")
        print("    - Klik kiri: Tambah titik zona")
        print("    - Klik kanan: Undo titik terakhir")
        print("    - SPACE: Selesai zona, mulai zona baru")
        print("    - S: Simpan zona → output di console")
        print("    - Q: Keluar tanpa simpan")

    def _resolve_youtube(self, url: str) -> str:
        """Resolve YouTube URL ke direct stream URL via yt-dlp."""
        import subprocess, shutil
        if not shutil.which("yt-dlp"):
            print("[ERROR] yt-dlp tidak ditemukan: pip install yt-dlp")
            exit(1)
        print("[yt-dlp] Mengambil stream URL...")
        cmd = ["yt-dlp", "-g", "-f", "best[height<=480]/best",
               "--no-warnings", "--no-playlist", url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            print(f"[ERROR] yt-dlp gagal: {res.stderr.strip()}")
            exit(1)
        urls = [u.strip() for u in res.stdout.strip().splitlines() if u.strip()]
        if not urls:
            print("[ERROR] Tidak ada URL yang didapat dari yt-dlp")
            exit(1)
        print(f"[yt-dlp] OK — stream URL didapat (480p untuk konfigurasi zona)")
        return urls[0]

    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events untuk menggambar zona"""
        if self.display_scale != 1.0:
            x = int(x / self.display_scale)
            y = int(y / self.display_scale)

        if event == cv2.EVENT_LBUTTONDOWN:
            self.points.append((x, y))
            print(f"  Point {len(self.points)}: ({x}, {y})")

        elif event == cv2.EVENT_RBUTTONDOWN:
            if self.points:
                removed = self.points.pop()
                print(f"  Removed: {removed}")

    def _update_display_scale(self):
        self.display_scale = min(
            self.max_display_width / self.width,
            self.max_display_height / self.height,
            1.0,
        )
        self.display_width = int(self.width * self.display_scale)
        self.display_height = int(self.height * self.display_scale)

    def run(self):
        """Main loop untuk konfigurasi zona"""
        self._update_display_scale()
        cv2.namedWindow("Zone Configurator", cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow("Zone Configurator", self.display_width, self.display_height)
        cv2.setMouseCallback("Zone Configurator", self.mouse_callback)

        zone_count = 1

        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("[*] Video selesai, rewind...")
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if not ret:
                    break

            display = frame.copy()

            # Draw existing zones
            for zone_name, zone_data in self.zones.items():
                pts = np.array(zone_data["polygon"], dtype=np.int32)
                cv2.polylines(display, [pts], True, zone_data["color"], 2)
                cv2.putText(display, zone_data["label"], zone_data["polygon"][0],
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, zone_data["color"], 2)

            # Draw current points
            for i, pt in enumerate(self.points):
                cv2.circle(display, pt, 5, (0, 255, 0), -1)
                cv2.putText(display, str(i + 1), (pt[0] + 10, pt[1]),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # Draw line preview
            if len(self.points) > 1:
                pts = np.array(self.points, dtype=np.int32)
                cv2.polylines(display, [pts], False, (0, 255, 0), 2)

            # Info panel
            h = 100
            cv2.rectangle(display, (0, 0), (display.shape[1], h), (30, 30, 30), -1)
            cv2.putText(display, "Zone Configurator - DISHUB DKI Jakarta",
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            info_text = f"Zone #{zone_count} | Points: {len(self.points)} | Zones saved: {len(self.zones)}"
            cv2.putText(display, info_text, (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            hint_text = "LEFT: +Point | RIGHT: -Point | SPACE: Next Zone | S: Save | Q: Quit"
            cv2.putText(display, hint_text, (10, 85),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 255), 1)

            if self.display_scale != 1.0:
                display = cv2.resize(
                    display,
                    (self.display_width, self.display_height),
                    interpolation=cv2.INTER_AREA,
                )

            cv2.imshow("Zone Configurator", display)
            self.frame = frame

            key = cv2.waitKey(30) & 0xFF

            if key == ord('q') or key == ord('Q'):
                print("[*] Keluar tanpa simpan.")
                break

            elif key == ord('s') or key == ord('S'):
                self.save_zones()
                break

            elif key == ord(' '):  # SPACE
                if len(self.points) >= 3:
                    # Zone colors
                    colors = [
                        (0, 0, 255),     # Red
                        (255, 165, 0),   # Orange
                        (255, 0, 255),   # Pink
                        (0, 255, 255),   # Cyan
                        (255, 255, 0),   # Blue (BGR)
                    ]
                    color = colors[len(self.zones) % len(colors)]

                    zone_name = f"ZONE_{zone_count}"
                    zone_label = f"Zone {zone_count}"

                    self.zones[zone_name] = {
                        "polygon": self.points.copy(),
                        "color": color,
                        "label": zone_label
                    }

                    print(f"[✓] Zone {zone_count} saved: {len(self.points)} points")
                    print(f"  Polygon: {self.points}")

                    self.points = []
                    zone_count += 1

                else:
                    print("[!] Minimal 3 titik untuk membuat zona!")

        cv2.destroyAllWindows()
        self.cap.release()

    def save_zones(self):
        """Simpan zona ke format yang bisa dicopy ke config.py"""
        if not self.zones:
            print("[!] Tidak ada zona untuk disimpan.")
            return

        print("\n" + "=" * 70)
        print("ZONE CONFIGURATION - Copy ke config.py")
        print("=" * 70)
        print("\nZONES = {")

        for zone_name, zone_data in self.zones.items():
            polygon = zone_data["polygon"]
            color = zone_data["color"]

            print(f'    "{zone_name}": {{')
            print(f'        "polygon": {polygon},')
            print(f'        "color": {color},')
            print(f'        "label": "{zone_data["label"]}",')
            print(f'        "violation_type": "zone_violation"  # EDIT MANUAL!')
            print('    },')

        print("}")
        print("\n" + "=" * 70)
        print("[✓] Configuration ready to use!")
        print("[→] Paste ke ZONES dictionary di config.py")
        print("[→] Edit violation_type sesuai zona (busway_violation, dll)")
        print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Zone Configurator - Setup zona deteksi untuk Traffic Enforcement"
    )
    parser.add_argument(
        "--source", "-s",
        default="0",
        help="Video source: 0 (webcam), file path, RTSP URL, atau YouTube URL"
    )
    args = parser.parse_args()

    # Parse source
    if args.source == "0":
        source = 0
    elif args.source.isdigit():
        source = int(args.source)
    else:
        source = args.source   # YouTube, file, RTSP — diserahkan ke ZoneConfigurator

    configurator = ZoneConfigurator(source)
    configurator.run()


if __name__ == "__main__":
    main()
