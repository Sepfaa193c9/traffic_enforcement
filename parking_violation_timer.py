# parking_violation_timer.py
# Logika timer parkir illegal - terintegrasi dengan detector.py

import time
from datetime import datetime
from collections import deque
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# ============================================================
# KONFIGURASI
# ============================================================

PARKING_CONFIG = {
    'parking_threshold_seconds': 180,   # 3 menit = parkir illegal
    'stopped_threshold_seconds': 10,    # 10 detik = stopped
    'max_history_length': 30,           # history posisi
    'zone_check_interval': 5,           # cek zone setiap N frame
}


class VehicleState:
    MOVING = 'moving'
    STOPPED = 'stopped'
    PARKING_ILLEGAL = 'parking_illegal'


class ParkingViolationTimer:
    """
    Timer untuk mendeteksi parkir illegal
    - Membedakan stopped (berhenti sebentar) vs parking (parkir)
    - Threshold waktu: 180 detik default
    - Zone detection using polygon
    """
    
    def __init__(self, config: dict = None):
        self.config = config or PARKING_CONFIG
        self.parking_threshold = self.config['parking_threshold_seconds']
        self.stopped_threshold = self.config['stopped_threshold_seconds']
        
        # Data storage per vehicle
        self.vehicles: Dict[int, dict] = {}
        self.violations: List[dict] = []
        
        # Zone data (akan diisi dari config.py ZONES)
        self.zones = []
        
        # Frame counter untuk throttling
        self._frame_counter = 0
        
        # Statistik
        self.stats = {
            'total_vehicles_tracked': 0,
            'total_violations': 0,
            'total_parking_minutes': 0
        }
    
    def set_zones(self, zones: dict):
        """
        Set zona parkir dari config.py ZONES
        zones format: {
            "zone_name": {
                "polygon": [(x1,y1), (x2,y2), ...],
                "violation_type": "illegal_parking"
            }
        }
        """
        self.zones = []
        for zone_name, zone_info in zones.items():
            if zone_info.get('violation_type') == 'illegal_parking':
                self.zones.append({
                    'name': zone_name,
                    'polygon': zone_info['polygon'],
                    'violation_type': zone_info.get('violation_type', 'illegal_parking')
                })
        logger.info(f"Parking timer initialized with {len(self.zones)} illegal parking zones")
    
    def _point_in_polygon(self, point: Tuple[float, float], polygon: List[Tuple]) -> bool:
        """Ray casting algorithm untuk cek titik dalam polygon"""
        x, y = point
        inside = False
        n = len(polygon)
        
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            
            # Check if point is on horizontal boundary
            if y1 == y2 and y == y1 and min(x1, x2) <= x <= max(x1, x2):
                return True
            
            # Check intersection
            if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
                inside = not inside
        
        return inside
    
    def _get_bbox_bottom_center(self, bbox: List[int]) -> Tuple[float, float]:
        """Dapatkan titik bawah tengah bounding box (pijakan kendaraan)"""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, y2)
    
    def _check_zone(self, position: Tuple[float, float]) -> Optional[dict]:
        """Cek apakah posisi di dalam zona parkir terlarang"""
        for zone in self.zones:
            if self._point_in_polygon(position, zone['polygon']):
                return zone
        return None
    
    def update(self, track_id: int, bbox: List[int], 
               vehicle_type: str = None, timestamp: float = None) -> dict:
        """
        Update status kendaraan
        
        Args:
            track_id: ID dari tracker
            bbox: [x1, y1, x2, y2]
            vehicle_type: 'car', 'motorcycle', dll
            timestamp: waktu (default now)
        
        Returns:
            dict dengan status dan info violation
        """
        if timestamp is None:
            timestamp = time.time()
        
        position = self._get_bbox_bottom_center(bbox)
        zone = self._check_zone(position)
        
        # Initialize vehicle if new
        if track_id not in self.vehicles:
            self.vehicles[track_id] = {
                'first_seen': timestamp,
                'last_seen': timestamp,
                'last_position': position,
                'state': VehicleState.MOVING,
                'stop_start_time': None,
                'vehicle_type': vehicle_type,
                'position_history': deque(maxlen=self.config['max_history_length']),
                'zone_enter_time': None,
                'current_zone': None,
                'license_plate': None
            }
            self.stats['total_vehicles_tracked'] += 1
        
        vehicle = self.vehicles[track_id]
        
        # Update vehicle type
        if vehicle['vehicle_type'] is None and vehicle_type:
            vehicle['vehicle_type'] = vehicle_type
        
        # Update position history
        vehicle['position_history'].append(position)
        
        # Calculate movement distance
        last_pos = vehicle['last_position']
        distance = ((position[0] - last_pos[0]) ** 2 + (position[1] - last_pos[1]) ** 2) ** 0.5
        is_moving = distance > 15  # threshold pixel
        
        # Check zone entry/exit
        if zone and not vehicle['current_zone']:
            # Entering violation zone
            vehicle['current_zone'] = zone
            vehicle['zone_enter_time'] = timestamp
            logger.debug(f"Vehicle {track_id} entered zone {zone['name']}")
        elif not zone and vehicle['current_zone']:
            # Exiting violation zone
            if vehicle['state'] == VehicleState.PARKING_ILLEGAL:
                # Record violation end
                duration = timestamp - vehicle['stop_start_time']
                self._record_violation(vehicle, timestamp, duration, vehicle['current_zone'])
            vehicle['current_zone'] = None
            vehicle['zone_enter_time'] = None
        
        # State machine
        result = self._update_state_machine(vehicle, is_moving, timestamp, track_id, zone)
        
        vehicle['last_seen'] = timestamp
        vehicle['last_position'] = position
        
        return result
    
    def _update_state_machine(self, vehicle: dict, is_moving: bool, 
                              timestamp: float, track_id: int, 
                              zone: Optional[dict]) -> dict:
        """State machine untuk deteksi parkir"""
        
        result = {
            'track_id': track_id,
            'state': vehicle['state'],
            'is_violation': False,
            'violation_type': None,
            'duration': 0,
            'zone': vehicle['current_zone']['name'] if vehicle['current_zone'] else None,
            'license_plate': vehicle.get('license_plate'),
            'vehicle_type': vehicle.get('vehicle_type')
        }
        
        # MOVING state
        if vehicle['state'] == VehicleState.MOVING:
            if not is_moving and vehicle['current_zone']:
                # Just stopped in violation zone
                vehicle['stop_start_time'] = timestamp
                vehicle['state'] = VehicleState.STOPPED
                result['state'] = VehicleState.STOPPED
        
        # STOPPED state
        elif vehicle['state'] == VehicleState.STOPPED:
            if is_moving:
                # Started moving again
                vehicle['state'] = VehicleState.MOVING
                vehicle['stop_start_time'] = None
                result['state'] = VehicleState.MOVING
            else:
                # Still stopped, check duration
                duration = timestamp - vehicle['stop_start_time']
                result['duration'] = duration
                
                # Check if exceeded parking threshold
                if duration >= self.parking_threshold and vehicle['current_zone']:
                    vehicle['state'] = VehicleState.PARKING_ILLEGAL
                    result['is_violation'] = True
                    result['violation_type'] = 'illegal_parking'
                    result['state'] = VehicleState.PARKING_ILLEGAL
                    result['duration'] = duration
                    
                    logger.info(f"⚠️ Parking violation! Vehicle {track_id} parked for {duration:.0f}s")
        
        # PARKING_ILLEGAL state
        elif vehicle['state'] == VehicleState.PARKING_ILLEGAL:
            if is_moving:
                # Vehicle leaving
                total_duration = timestamp - vehicle['stop_start_time']
                result['violation_ended'] = True
                result['total_duration'] = total_duration
                
                vehicle['state'] = VehicleState.MOVING
                vehicle['stop_start_time'] = None
            else:
                # Still parking illegal
                duration = timestamp - vehicle['stop_start_time']
                result['duration'] = duration
                result['is_violation'] = True
                result['zone'] = vehicle['current_zone']['name'] if vehicle['current_zone'] else None
        
        return result
    
    def _record_violation(self, vehicle: dict, timestamp: float, 
                          duration: float, zone: dict):
        """Record violation ke history"""
        violation = {
            'timestamp': datetime.fromtimestamp(timestamp),
            'timestamp_float': timestamp,
            'duration_seconds': round(duration, 1),
            'duration_minutes': round(duration / 60, 1),
            'zone': zone['name'],
            'vehicle_type': vehicle['vehicle_type'],
            'license_plate': vehicle.get('license_plate', 'UNKNOWN')
        }
        self.violations.append(violation)
        self.stats['total_violations'] += 1
        self.stats['total_parking_minutes'] += violation['duration_minutes']
    
    def set_license_plate(self, track_id: int, plate: str):
        """Set license plate untuk kendaraan"""
        if track_id in self.vehicles:
            self.vehicles[track_id]['license_plate'] = plate
    
    def get_active_violations(self) -> List[dict]:
        """Dapatkan kendaraan yang sedang parkir illegal"""
        active = []
        now = time.time()
        
        for track_id, vehicle in self.vehicles.items():
            if vehicle['state'] == VehicleState.PARKING_ILLEGAL:
                duration = now - vehicle['stop_start_time']
                active.append({
                    'track_id': track_id,
                    'duration_seconds': round(duration, 1),
                    'vehicle_type': vehicle['vehicle_type'],
                    'license_plate': vehicle.get('license_plate', 'UNKNOWN'),
                    'zone': vehicle['current_zone']['name'] if vehicle['current_zone'] else None
                })
        
        return active
    
    def get_statistics(self) -> dict:
        """Dapatkan statistik parkir illegal"""
        if not self.violations:
            return {
                'total_violations': 0,
                'total_vehicles_tracked': self.stats['total_vehicles_tracked'],
                'average_duration_minutes': 0,
                'max_duration_minutes': 0,
                'total_parking_hours': 0,
                'violations_per_zone': {}
            }
        
        durations = [v['duration_minutes'] for v in self.violations]
        
        # Per zone
        from collections import Counter
        zones = Counter([v['zone'] for v in self.violations if v['zone']])
        
        return {
            'total_violations': len(self.violations),
            'total_vehicles_tracked': self.stats['total_vehicles_tracked'],
            'average_duration_minutes': round(sum(durations) / len(durations), 1),
            'max_duration_minutes': round(max(durations), 1),
            'total_parking_hours': round(self.stats['total_parking_minutes'] / 60, 1),
            'violations_per_zone': dict(zones)
        }
    
    def remove_track(self, track_id: int):
        """Hapus vehicle yang sudah tidak terdeteksi"""
        if track_id in self.vehicles:
            del self.vehicles[track_id]
    
    def cleanup_stale_tracks(self, active_ids: set, max_age_seconds: int = 60):
        """Bersihkan track yang sudah lama tidak terlihat"""
        now = time.time()
        stale = []
        
        for track_id, vehicle in self.vehicles.items():
            if track_id not in active_ids:
                if now - vehicle['last_seen'] > max_age_seconds:
                    stale.append(track_id)
        
        for track_id in stale:
            self.remove_track(track_id)
        
        if stale:
            logger.debug(f"Cleaned up {len(stale)} stale tracks")
        
        return len(stale)
    
    def get_violations_for_dashboard(self, hours_back: int = 24) -> List[dict]:
        """Dapatkan violations untuk dashboard (filter by hours)"""
        if not self.violations:
            return []
        
        cutoff = time.time() - (hours_back * 3600)
        return [v for v in self.violations if v['timestamp_float'] >= cutoff]