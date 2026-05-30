# heatmap_dashboard.py
# Modul heatmap dan temporal pattern untuk dashboard
# Terintegrasi dengan dashboard.py yang sudah ada

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# ============================================================
# ANALISIS TEMPORAL
# ============================================================

class TemporalAnalyzer:
    """
    Analisis temporal pattern pelanggaran untuk dashboard
    """
    
    def __init__(self, df: pd.DataFrame = None):
        self.df = df
        if self.df is not None and not self.df.empty:
            self._prepare_data()
    
    def _prepare_data(self):
        """Prepare dataframe untuk analisis"""
        if 'timestamp' in self.df.columns:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            self.df['hour'] = self.df['timestamp'].dt.hour
            self.df['day_of_week'] = self.df['timestamp'].dt.dayofweek
            self.df['day_name'] = self.df['timestamp'].dt.day_name()
            self.df['week'] = self.df['timestamp'].dt.isocalendar().week
            self.df['month'] = self.df['timestamp'].dt.month
            self.df['date'] = self.df['timestamp'].dt.date
    
    def set_data(self, df: pd.DataFrame):
        """Set data untuk analisis"""
        self.df = df
        if self.df is not None and not self.df.empty:
            self._prepare_data()
    
    def get_peak_hours(self, top_n: int = 3) -> Dict:
        """Dapatkan jam sibuk pelanggaran"""
        if self.df is None or self.df.empty:
            return {'peak_hours': [], 'peak_hour_counts': {}, 'off_peak_hour': None, 'hourly_distribution': {}}
        
        hourly = self.df.groupby('hour').size()
        hourly_dict = {int(h): int(c) for h, c in hourly.items()}
        
        # Isi jam yang kosong
        for h in range(24):
            if h not in hourly_dict:
                hourly_dict[h] = 0
        
        sorted_hours = sorted(hourly_dict.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'peak_hours': [h for h, _ in sorted_hours[:top_n]],
            'peak_hour_counts': {h: c for h, c in sorted_hours[:top_n]},
            'off_peak_hour': sorted_hours[-1][0] if sorted_hours else None,
            'hourly_distribution': hourly_dict
        }
    
    def get_daily_pattern(self) -> Dict:
        """Dapatkan pattern harian"""
        if self.df is None or self.df.empty:
            return {}
        
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily = self.df.groupby('day_name').size()
        daily = daily.reindex(day_order).fillna(0)
        
        weekday_total = daily[['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']].sum()
        weekend_total = daily[['Saturday', 'Sunday']].sum()
        
        return {
            'by_day': {k: int(v) for k, v in daily.items()},
            'busiest_day': daily.idxmax(),
            'busiest_day_count': int(daily.max()),
            'quietest_day': daily.idxmin(),
            'weekend_ratio': round(weekend_total / weekday_total, 2) if weekday_total > 0 else 0
        }
    
    def get_hourly_heatmap_data(self) -> pd.DataFrame:
        """Dapatkan matrix untuk heatmap (day × hour)"""
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        # Pivot table
        pivot = self.df.pivot_table(
            index='day_name',
            columns='hour',
            values='id' if 'id' in self.df.columns else 'timestamp',
            aggfunc='count',
            fill_value=0
        )
        
        # Urutkan hari
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        pivot = pivot.reindex([d for d in day_order if d in pivot.index])
        
        # Pastikan semua jam 0-23 ada
        for h in range(24):
            if h not in pivot.columns:
                pivot[h] = 0
        
        pivot = pivot[sorted(pivot.columns)]
        
        return pivot
    
    def get_weekly_trend(self) -> pd.DataFrame:
        """Dapatkan trend mingguan"""
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        weekly = self.df.groupby('week').size().reset_index()
        weekly.columns = ['week', 'total']
        weekly = weekly.sort_values('week')
        weekly['change_percent'] = weekly['total'].pct_change() * 100
        weekly['change_percent'] = weekly['change_percent'].round(1)
        
        return weekly
    
    def get_temporal_summary(self) -> Dict:
        """Dapatkan ringkasan temporal lengkap"""
        peak = self.get_peak_hours()
        daily = self.get_daily_pattern()
        
        return {
            'peak_hours': peak,
            'daily_pattern': daily,
            'busiest_hour': peak['peak_hours'][0] if peak['peak_hours'] else None,
            'busiest_day': daily.get('busiest_day'),
            'weekend_ratio': daily.get('weekend_ratio', 0)
        }


# ============================================================
# HEATMAP GENERATOR
# ============================================================

class HeatmapGenerator:
    """
    Generator heatmap untuk Folium (dashboard.py)
    """
    
    def __init__(self, df: pd.DataFrame = None):
        self.df = df
    
    def set_data(self, df: pd.DataFrame):
        """Set data violations dengan latitude/longitude"""
        self.df = df
    
    def generate_heatmap_data(self) -> List[List[float]]:
        """
        Generate data untuk heatmap
        Returns: list of [lat, lon, intensity]
        """
        if self.df is None or self.df.empty:
            return []
        
        heat_data = []
        
        for _, row in self.df.iterrows():
            lat = row.get('latitude')
            lon = row.get('longitude')
            
            if lat is not None and lon is not None and not pd.isna(lat) and not pd.isna(lon):
                # Intensity berdasarkan durasi atau default 1
                intensity = row.get('duration_seconds', 60) / 60  # menit
                intensity = min(intensity, 5)  # cap di 5
                heat_data.append([float(lat), float(lon), intensity])
        
        return heat_data
    
    def get_hotspots(self, top_n: int = 5) -> List[Dict]:
        """
        Dapatkan hotspot (area dengan pelanggaran terbanyak)
        
        Returns:
            List of dict dengan camera_id, name, lat, lon, count
        """
        if self.df is None or self.df.empty:
            return []
        
        # Group by camera
        hotspots = []
        
        for camera_id, group in self.df.groupby('camera_id'):
            lat = group['latitude'].iloc[0] if 'latitude' in group.columns and not group['latitude'].isna().all() else None
            lon = group['longitude'].iloc[0] if 'longitude' in group.columns and not group['longitude'].isna().all() else None
            
            if lat is not None and lon is not None:
                hotspots.append({
                    'camera_id': camera_id,
                    'name': f"Camera {camera_id}",
                    'lat': float(lat),
                    'lon': float(lon),
                    'count': len(group)
                })
        
        hotspots.sort(key=lambda x: x['count'], reverse=True)
        return hotspots[:top_n]
    
    def get_heatmap_stats(self) -> Dict:
        """Dapatkan statistik untuk heatmap"""
        if self.df is None or self.df.empty:
            return {'total_locations': 0, 'max_intensity': 0, 'avg_intensity': 0}
        
        heat_data = self.generate_heatmap_data()
        intensities = [d[2] for d in heat_data] if heat_data else [0]
        
        return {
            'total_locations': len(heat_data),
            'max_intensity': round(max(intensities), 2) if intensities else 0,
            'avg_intensity': round(sum(intensities) / len(intensities), 2) if intensities else 0
        }


# ============================================================
# REKOMENDASI PENEMPATAN ETLE
# ============================================================

class ETLEPlacementRecommender:
    """
    Sistem rekomendasi penempatan ETLE berdasarkan data pelanggaran
    """
    
    def __init__(self, df: pd.DataFrame = None, camera_locations: dict = None):
        self.df = df
        self.camera_locations = camera_locations or {}
    
    def set_data(self, df: pd.DataFrame, camera_locations: dict = None):
        self.df = df
        if camera_locations:
            self.camera_locations = camera_locations
    
    def get_recommendations(self, top_n: int = 5) -> List[Dict]:
        """
        Dapatkan rekomendasi penempatan ETLE mobile
        
        Returns:
            List of dict dengan:
            - location_name
            - priority (high/medium/low)
            - reason
            - recommended_units
            - peak_hours
        """
        if self.df is None or self.df.empty:
            return []
        
        recommendations = []
        
        # Group by camera/location
        for camera_id, group in self.df.groupby('camera_id'):
            camera_info = self.camera_locations.get(camera_id, {})
            
            # Hitung skor prioritas
            total_violations = len(group)
            
            # Hitung jam sibuk untuk lokasi ini
            group['hour'] = pd.to_datetime(group['timestamp']).dt.hour
            peak_hours = group['hour'].value_counts().head(3).index.tolist()
            
            # Hitung jenis pelanggaran dominan
            violation_types = group['violation_type'].value_counts()
            dominant_violation = violation_types.index[0] if not violation_types.empty else None
            
            # Tentukan prioritas
            if total_violations >= 100:
                priority = 'high'
                units = 2
            elif total_violations >= 50:
                priority = 'medium'
                units = 1
            else:
                priority = 'low'
                units = 1
            
            # Reason
            reason = f"{total_violations} pelanggaran dalam 30 hari"
            if dominant_violation == 'illegal_parking':
                reason += ", dominan parkir liar"
            elif dominant_violation == 'busway_violation':
                reason += ", dominan pelanggaran jalur busway"
            
            recommendations.append({
                'location_name': camera_info.get('name', camera_id),
                'camera_id': camera_id,
                'latitude': camera_info.get('lat'),
                'longitude': camera_info.get('lon'),
                'priority': priority,
                'priority_score': total_violations,
                'reason': reason,
                'recommended_units': units,
                'peak_hours': peak_hours,
            })