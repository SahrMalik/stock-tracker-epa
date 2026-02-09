"""
Integration tests for stock scanner Lambda function.
Tests AWS service integrations (S3, DynamoDB, SNS).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda'))

import pytest
import boto3
from moto import mock_aws
import json
from datetime import datetime

# Import functions from Lambda
from stock_scanner import store_raw_data_with_retry


@mock_aws
class TestS3Integration:
    """Test S3 integration."""
    
    def setup_method(self, method):
        """Set up S3 bucket for testing."""
        self.s3 = boto3.client('s3', region_name='us-east-1')
        self.bucket_name = 'stock-scan-data-529088281783'
        self.s3.create_bucket(Bucket=self.bucket_name)
        os.environ['S3_BUCKET'] = self.bucket_name
    
    def test_store_raw_data_success(self):
        """Test successful storage of raw data in S3."""
        data = [
            {'date': '2026-01-01', 'close': 150.0, 'volume': 50000000},
            {'date': '2026-01-02', 'close': 151.0, 'volume': 51000000}
        ]
        
        s3_key = store_raw_data_with_retry('AAPL', data)
        
        # Verify key format
        assert s3_key.startswith('raw-data/AAPL/')
        assert s3_key.endswith('.json')
        
        # Verify data was stored
        response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
        stored_data = json.loads(response['Body'].read())
        
        assert len(stored_data) == 2
        assert stored_data[0]['close'] == 150.0
    
    def test_store_raw_data_with_large_dataset(self):
        """Test storage of large dataset."""
        data = [
            {'date': f'2026-01-{i:02d}', 'close': 150.0 + i, 'volume': 50000000}
            for i in range(1, 31)
        ]
        
        s3_key = store_raw_data_with_retry('AAPL', data)
        
        # Verify data was stored
        response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
        stored_data = json.loads(response['Body'].read())
        
        assert len(stored_data) == 30


@mock_aws
class TestDynamoDBIntegration:
    """Test DynamoDB integration."""
    
    def setup_method(self, method):
        """Set up DynamoDB table for testing."""
        self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Create table
        self.table = self.dynamodb.create_table(
            TableName='stock-anomalies',
            KeySchema=[
                {'AttributeName': 'ticker', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'ticker', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
    
    def test_store_anomaly_in_dynamodb(self):
        """Test storing anomaly in DynamoDB."""
        anomaly = {
            'ticker': 'AAPL',
            'timestamp': datetime.utcnow().isoformat(),
            'date': '2026-01-21',
            'anomaly_type': 'price',
            'value': 160.0,
            'baseline_mean': 150.0,
            'baseline_std': 2.0,
            'z_score': 5.0,
            'threshold': 2.0,
            'severity': 'high'
        }
        
        # Store anomaly
        self.table.put_item(Item=anomaly)
        
        # Retrieve and verify
        response = self.table.get_item(
            Key={
                'ticker': anomaly['ticker'],
                'timestamp': anomaly['timestamp']
            }
        )
        
        assert 'Item' in response
        assert response['Item']['anomaly_type'] == 'price'
        assert float(response['Item']['value']) == 160.0
    
    def test_query_anomalies_by_ticker(self):
        """Test querying anomalies by ticker."""
        # Store multiple anomalies
        for i in range(3):
            anomaly = {
                'ticker': 'AAPL',
                'timestamp': f'2026-01-{i+1:02d}T10:00:00',
                'date': f'2026-01-{i+1:02d}',
                'anomaly_type': 'price',
                'value': 160.0 + i,
                'z_score': 5.0
            }
            self.table.put_item(Item=anomaly)
        
        # Query by ticker
        response = self.table.query(
            KeyConditionExpression='ticker = :ticker',
            ExpressionAttributeValues={':ticker': 'AAPL'}
        )
        
        assert response['Count'] == 3


@mock_aws
class TestSNSIntegration:
    """Test SNS integration."""
    
    def setup_method(self, method):
        """Set up SNS topic for testing."""
        self.sns = boto3.client('sns', region_name='us-east-1')
        
        # Create topic
        response = self.sns.create_topic(Name='stock-tracker-alerts')
        self.topic_arn = response['TopicArn']
        os.environ['SNS_TOPIC_ARN'] = self.topic_arn
    
    def test_publish_alert_to_sns(self):
        """Test publishing alert to SNS."""
        message = "Test anomaly alert"
        
        response = self.sns.publish(
            TopicArn=self.topic_arn,
            Subject='Test Alert',
            Message=message
        )
        
        assert 'MessageId' in response
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
