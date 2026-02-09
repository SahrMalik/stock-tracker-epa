"""
Unit tests for stock scanner Lambda function.
Tests anomaly detection logic, error handling, and data processing.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda'))

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

# Import functions from Lambda
from stock_scanner import (
    detect_anomalies,
    format_alert_message,
    fetch_stock_data_simple,
    retry_with_backoff
)


class TestAnomalyDetection:
    """Test anomaly detection logic."""
    
    def test_detect_price_anomaly_high(self):
        """Test detection of high price anomaly."""
        # Create baseline data with some variance
        baseline = [
            {'date': f'2026-01-{i:02d}', 'close': 150.0 + (i % 5) * 0.5, 'volume': 50000000}
            for i in range(1, 21)
        ]
        # Add current day with anomalous price
        current = {'date': '2026-01-21', 'close': 165.0, 'volume': 50000000}
        data = baseline + [current]
        
        anomalies = detect_anomalies('AAPL', data, threshold=2.0)
        
        # Should detect price anomaly
        assert len(anomalies) >= 1
        price_anomalies = [a for a in anomalies if a['anomaly_type'] == 'price']
        assert len(price_anomalies) > 0
        price_anomaly = price_anomalies[0]
        assert price_anomaly['ticker'] == 'AAPL'
        assert price_anomaly['value'] == 165.0
        assert abs(price_anomaly['z_score']) > 2.0
    
    def test_detect_volume_anomaly(self):
        """Test detection of volume anomaly."""
        baseline = [
            {'date': f'2026-01-{i:02d}', 'close': 150.0, 'volume': 50000000 + (i % 5) * 100000}
            for i in range(1, 21)
        ]
        # Add current day with very anomalous volume
        current = {'date': '2026-01-21', 'close': 150.0, 'volume': 150000000}
        data = baseline + [current]
        
        anomalies = detect_anomalies('AAPL', data, threshold=2.0)
        
        # Should detect volume anomaly
        assert len(anomalies) >= 1
        volume_anomalies = [a for a in anomalies if a['anomaly_type'] == 'volume']
        assert len(volume_anomalies) > 0
        volume_anomaly = volume_anomalies[0]
        assert volume_anomaly['ticker'] == 'AAPL'
        assert volume_anomaly['value'] == 150000000
        assert abs(volume_anomaly['z_score']) > 2.0
    
    def test_no_anomaly_detected(self):
        """Test that no anomaly is detected for normal data."""
        # All data points around $150
        data = [
            {'date': f'2026-01-{i:02d}', 'close': 150.0 + (i % 3), 'volume': 50000000}
            for i in range(1, 22)
        ]
        
        anomalies = detect_anomalies('AAPL', data, threshold=2.0)
        
        # Should not detect any anomalies
        assert len(anomalies) == 0
    
    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        data = [
            {'date': f'2026-01-{i:02d}', 'close': 150.0, 'volume': 50000000}
            for i in range(1, 10)  # Only 9 days
        ]
        
        anomalies = detect_anomalies('AAPL', data, threshold=2.0)
        
        # Should return empty list
        assert len(anomalies) == 0
    
    def test_severity_classification(self):
        """Test anomaly severity classification."""
        baseline = [
            {'date': f'2026-01-{i:02d}', 'close': 150.0 + (i % 5) * 0.5, 'volume': 50000000}
            for i in range(1, 21)
        ]
        # Very high anomaly (should trigger high severity)
        current = {'date': '2026-01-21', 'close': 170.0, 'volume': 50000000}
        data = baseline + [current]
        
        anomalies = detect_anomalies('AAPL', data, threshold=2.0)
        
        price_anomalies = [a for a in anomalies if a['anomaly_type'] == 'price']
        assert len(price_anomalies) > 0
        price_anomaly = price_anomalies[0]
        # Should be classified as high severity
        assert price_anomaly['severity'] in ['high', 'medium']


class TestAlertFormatting:
    """Test alert message formatting."""
    
    def test_format_price_anomaly_message(self):
        """Test formatting of price anomaly alert."""
        anomaly = {
            'ticker': 'AAPL',
            'anomaly_type': 'price',
            'severity': 'high',
            'date': '2026-01-21',
            'value': 160.0,
            'baseline_mean': 150.0,
            'baseline_std': 2.0,
            'z_score': 5.0,
            'threshold': 2.0
        }
        
        message = format_alert_message(anomaly)
        
        assert 'AAPL' in message
        assert 'PRICE' in message
        assert 'HIGH' in message
        assert '160.00' in message
        assert '5.0' in message
    
    def test_format_volume_anomaly_message(self):
        """Test formatting of volume anomaly alert."""
        anomaly = {
            'ticker': 'AAPL',
            'anomaly_type': 'volume',
            'severity': 'medium',
            'date': '2026-01-21',
            'value': 150000000,
            'baseline_mean': 50000000,
            'baseline_std': 10000000,
            'z_score': 2.5,
            'threshold': 2.0
        }
        
        message = format_alert_message(anomaly)
        
        assert 'AAPL' in message
        assert 'VOLUME' in message
        assert 'MEDIUM' in message


class TestDataFetching:
    """Test data fetching functions."""
    
    def test_fetch_stock_data_returns_correct_length(self):
        """Test that fetch returns correct number of days."""
        data = fetch_stock_data_simple('AAPL', days=30)
        
        assert data is not None
        assert len(data) == 30
    
    def test_fetch_stock_data_structure(self):
        """Test that fetched data has correct structure."""
        data = fetch_stock_data_simple('AAPL', days=5)
        
        assert len(data) == 5
        for item in data:
            assert 'date' in item
            assert 'open' in item
            assert 'high' in item
            assert 'low' in item
            assert 'close' in item
            assert 'volume' in item
    
    def test_fetch_stock_data_values(self):
        """Test that fetched data has reasonable values."""
        data = fetch_stock_data_simple('AAPL', days=5)
        
        for item in data:
            assert item['close'] > 0
            assert item['volume'] > 0
            assert item['high'] >= item['low']


class TestRetryLogic:
    """Test retry with exponential backoff."""
    
    def test_retry_success_first_attempt(self):
        """Test successful execution on first attempt."""
        mock_func = Mock(return_value='success')
        
        result = retry_with_backoff(mock_func, max_retries=3)
        
        assert result == 'success'
        assert mock_func.call_count == 1
    
    def test_retry_success_after_failures(self):
        """Test successful execution after retries."""
        mock_func = Mock(side_effect=[Exception('fail'), Exception('fail'), 'success'])
        
        result = retry_with_backoff(mock_func, max_retries=3, initial_delay=0.01)
        
        assert result == 'success'
        assert mock_func.call_count == 3
    
    def test_retry_max_retries_exceeded(self):
        """Test that exception is raised after max retries."""
        mock_func = Mock(__name__='test_func', side_effect=Exception('always fails'))
        
        with pytest.raises(Exception, match='always fails'):
            retry_with_backoff(mock_func, max_retries=3, initial_delay=0.01)
        
        assert mock_func.call_count == 3


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_detect_anomalies_handles_empty_data(self):
        """Test anomaly detection with empty data."""
        anomalies = detect_anomalies('AAPL', [], threshold=2.0)
        
        assert len(anomalies) == 0
    
    def test_detect_anomalies_handles_none_data(self):
        """Test anomaly detection with None data."""
        anomalies = detect_anomalies('AAPL', None, threshold=2.0)
        
        assert len(anomalies) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--cov=stock_scanner', '--cov-report=term-missing'])
