# mock_api_integration.py
# Mock API untuk integrasi ETLE & Unit Derek Dishub

import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

logger = logging.getLogger(__name__)

# ============================================================
# ETLE INTEGRATION
# ============================================================

class ETLEIntegration:
    """
    Mock API untuk integrasi dengan sistem ETLE
    Bisa diganti dengan API real di production
    """
    
    def __init__(self, api_endpoint: str = None, api_key: str = None):
        self.api_endpoint = api_endpoint or "https://api-etle.dishub.go.id/v1"
        self.api_key = api_key or "MOCK_API_KEY_FOR_DEMO"
        self.sent_violations = []
        self.tickets = []
    
    def send_violation(self, violation_data: dict) -> dict:
        """
        Kirim data pelanggaran ke ETLE
        
        Args:
            violation_data: dict dengan keys:
                - license_plate (str)
                - vehicle_type (str)
                - violation_type (str)
                - location (str)
                - latitude (float)
                - longitude (float)
                - timestamp (datetime)
                - duration_seconds (int, optional)
        
        Returns:
            {'success': bool, 'ticket_id': str, 'message': str}
        """
        try:
            # Generate ticket ID
            ticket_id = f"ETLE-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
            
            # Simulasi proses
            ticket = {
                'ticket_id': ticket_id,
                'license_plate': violation_data.get('license_plate'),
                'violation_type': violation_data.get('violation_type'),
                'location': violation_data.get('location'),
                'timestamp': violation_data.get('timestamp').isoformat() if violation_data.get('timestamp') else None,
                'fine_amount': self._get_fine_amount(violation_data.get('violation_type')),
                'due_date': (datetime.now() + timedelta(days=14)).isoformat(),
                'status': 'issued'
            }
            
            self.tickets.append(ticket)
            self.sent_violations.append({
                'ticket_id': ticket_id,
                'violation': violation_data,
                'sent_at': datetime.now()
            })
            
            logger.info(f"ETLE Ticket generated: {ticket_id}")
            
            return {
                'success': True,
                'ticket_id': ticket_id,
                'message': 'Violation sent to ETLE system',
                'fine_amount': ticket['fine_amount'],
                'due_date': ticket['due_date']
            }
            
        except Exception as e:
            logger.error(f"ETLE error: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    def _get_fine_amount(self, violation_type: str) -> int:
        """Denda berdasarkan jenis pelanggaran"""
        fines = {
            'illegal_parking': 500000,
            'busway_violation': 500000,
            'wrong_way': 500000,
            'bike_lane_violation': 250000,
            'red_light': 500000,
            'speeding': 500000
        }
        return fines.get(violation_type, 500000)
    
    def check_ticket_status(self, ticket_id: str) -> dict:
        """Cek status tiket"""
        for ticket in self.tickets:
            if ticket['ticket_id'] == ticket_id:
                return ticket
        return {'status': 'not_found', 'message': 'Ticket not found'}
    
    def get_statistics(self) -> dict:
        """Dapatkan statistik ETLE"""
        return {
            'total_sent': len(self.sent_violations),
            'total_tickets': len(self.tickets),
            'pending_payment': sum(1 for t in self.tickets if t.get('status') == 'issued'),
            'paid': sum(1 for t in self.tickets if t.get('status') == 'paid')
        }


# ============================================================
# TOW TRUCK INTEGRATION
# ============================================================

class TowTruckIntegration:
    """
    Mock API untuk integrasi dengan unit derek Dishub
    """
    
    def __init__(self, api_endpoint: str = None):
        self.api_endpoint = api_endpoint or "https://api-dishub.go.id/v1/tow"
        self.active_requests = []
        self.completed_requests = []
    
    def request_tow_truck(self, request_data: dict) -> dict:
        """
        Request unit derek
        
        Args:
            request_data: dict dengan keys:
                - location (str)
                - license_plate (str)
                - vehicle_type (str)
                - reason (str)
                - priority (str): 'high', 'medium', 'low'
        
        Returns:
            {'success': bool, 'request_id': str, 'eta_minutes': int, 'message': str}
        """
        priority = request_data.get('priority', 'medium')
        
        # ETA based on priority
        eta_map = {'high': 15, 'medium': 30, 'low': 45}
        eta_minutes = eta_map.get(priority, 30)
        
        request_id = f"TOW-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"
        
        request = {
            'request_id': request_id,
            'location': request_data.get('location'),
            'license_plate': request_data.get('license_plate'),
            'vehicle_type': request_data.get('vehicle_type'),
            'reason': request_data.get('reason'),
            'priority': priority,
            'eta_minutes': eta_minutes,
            'status': 'assigned',
            'created_at': datetime.now().isoformat()
        }
        
        self.active_requests.append(request)
        
        logger.info(f"Tow truck requested: {request_id} for {request_data.get('license_plate')}")
        
        return {
            'success': True,
            'request_id': request_id,
            'eta_minutes': eta_minutes,
            'message': f"Unit derek dalam perjalanan, estimasi {eta_minutes} menit"
        }
    
    def check_status(self, request_id: str) -> dict:
        """Cek status request derek"""
        for req in self.active_requests:
            if req['request_id'] == request_id:
                return req
        
        for req in self.completed_requests:
            if req['request_id'] == request_id:
                return req
        
        return {'status': 'not_found', 'message': 'Request not found'}
    
    def complete_request(self, request_id: str) -> dict:
        """Tandai request sebagai selesai"""
        for i, req in enumerate(self.active_requests):
            if req['request_id'] == request_id:
                req['status'] = 'completed'
                req['completed_at'] = datetime.now().isoformat()
                self.completed_requests.append(req)
                self.active_requests.pop(i)
                return {'success': True, 'message': 'Request completed'}
        
        return {'success': False, 'message': 'Request not found'}
    
    def get_statistics(self) -> dict:
        """Dapatkan statistik unit derek"""
        return {
            'active_requests': len(self.active_requests),
            'completed_today': len([r for r in self.completed_requests 
                                   if datetime.fromisoformat(r['created_at']).date() == datetime.now().date()]),
            'total_requests': len(self.active_requests) + len(self.completed_requests)
        }


# ============================================================
# PUBLIC COMPLAINT NLP (SEDERHANA)
# ============================================================

class PublicComplaintNLP:
    """
    Klasifikasi keluhan masyarakat sederhana
    Tanpa library berat (rule-based)
    """
    
    def __init__(self):
        self.categories = {
            'illegal_parking': ['parkir', 'terparkir', 'berhenti', 'stop', 'dipinggir', 'bahu jalan'],
            'wrong_way': ['lawan arah', 'salah arah', 'melawan', 'berlawanan'],
            'busway_violation': ['busway', 'bus way', 'jalur bus', 'koridor'],
            'red_light': ['lampu merah', 'stopan merah', 'nerobos merah'],
            'speeding': ['ngebut', 'kencang', 'cepat', 'balap', 'speed'],
            'bike_lane': ['sepeda', 'bike lane', 'jalur sepeda'],
            'no_helmet': ['helm', 'tanpa helm', 'tidak pakai helm'],
            'no_license': ['SIM', 'STNK', 'surat', 'dokumen']
        }
    
    def classify_complaint(self, text: str) -> dict:
        """
        Klasifikasi keluhan masyarakat
        
        Args:
            text: teks keluhan
        
        Returns:
            {'category': str, 'confidence': float, 'extracted_plate': str or None}
        """
        text_lower = text.lower()
        
        # Extract plate number (sederhana)
        plate_pattern = r'([A-Z]{1,2})\s*(\d{1,4})\s*([A-Z]{1,3})'
        plate_match = re.search(plate_pattern, text.upper())
        extracted_plate = plate_match.group(0) if plate_match else None
        
        # Classify
        scores = {}
        for category, keywords in self.categories.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[category] = score
        
        if scores:
            best_category = max(scores, key=scores.get)
            confidence = min(scores[best_category] / 3, 0.95)
        else:
            best_category = 'other'
            confidence = 0.3
        
        return {
            'category': best_category,
            'confidence': round(confidence, 2),
            'extracted_plate': extracted_plate,
            'original_text': text[:200]
        }
    
    def batch_classify(self, complaints: List[str]) -> List[dict]:
        """Klasifikasi banyak keluhan"""
        return [self.classify_complaint(c) for c in complaints]
    
    def get_summary(self, complaints: List[dict]) -> dict:
        """Dapatkan ringkasan keluhan"""
        if not complaints:
            return {}
        
        categories = [c['category'] for c in complaints]
        from collections import Counter
        category_counts = Counter(categories)
        
        return {
            'total_complaints': len(complaints),
            'category_distribution': dict(category_counts),
            'top_category': category_counts.most_common(1)[0][0] if category_counts else None,
            'complaints_with_plate': sum(1 for c in complaints if c.get('extracted_plate'))
        }


# ============================================================
# TEST CODE
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Mock API Integration Test")
    print("=" * 50)
    
    # Test ETLE
    print("\n📡 ETLE Integration:")
    etle = ETLEIntegration()
    result = etle.send_violation({
        'license_plate': 'B 1234 ABC',
        'vehicle_type': 'car',
        'violation_type': 'illegal_parking',
        'location': 'Jl. Sudirman',
        'latitude': -6.2088,
        'longitude': 106.8456,
        'timestamp': datetime.now(),
        'duration_seconds': 300
    })
    print(f"  {result}")
    
    # Test Tow Truck
    print("\n🚚 Tow Truck Integration:")
    tow = TowTruckIntegration()
    result = tow.request_tow_truck({
        'location': 'Jl. Thamrin No. 10',
        'license_plate': 'B 1234 ABC',
        'vehicle_type': 'car',
        'reason': 'Parkir liar di zona terlarang selama 10 menit',
        'priority': 'high'
    })
    print(f"  {result}")
    
    # Test Complaint NLP
    print("\n💬 Public Complaint NLP:")
    nlp = PublicComplaintNLP()
    complaints = [
        "Mobil B 1234 ABC parkir di bahu jalan Sudirman sudah 2 jam",
        "Motor melawan arah di Thamrin jam 8 pagi",
        "Bus masuk jalur busway padahal bukan waktunya"
    ]
    
    for complaint in complaints:
        result = nlp.classify_complaint(complaint)
        print(f"  '{complaint[:40]}...' → {result['category']} ({result['confidence']})")
    
    print("\n✅ Mock API modules ready!")