"""
Integration tests for stock scanner Lambda function.
Tests AWS service integrations (S3, DynamoDB, SNS).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda')) # Lambda file location

import pytest # Testing framework
import boto3 # AWS SDK to create mock AWS resources in tests
from moto import mock_aws # Intercepts all AWS API calls and runs them against dummy services
import json # Parse JSON data stored in mock S3
from datetime import datetime # For creating timestamps for test data

# Import functions from Lambda
from stock_scanner import store_raw_data_with_retry


@mock_aws
class TestS3Integration:
    """Test S3 integration."""
    
    def setup_method(self, method): # Runs automatically before each test to create a fresh mock environment
        """Set up S3 bucket for testing."""
        self.s3 = boto3.client('s3', region_name='us-east-1') # Creates S3 client
        self.bucket_name = 'stock-scan-data-529088281783' # Uses same bucket name as prod
        self.s3.create_bucket(Bucket=self.bucket_name) # Creates mock S3 bucket. In prod this is created by CDK
        os.environ['S3_BUCKET'] = self.bucket_name # Sets environment variable
    
    def test_store_raw_data_success(self):
        """Test successful storage of raw data in S3."""
        data = [
            {'date': '2026-01-01', 'close': 150.0, 'volume': 50000000},
            {'date': '2026-01-02', 'close': 151.0, 'volume': 51000000}
        ] # Creation of fake stock data
        
        s3_key = store_raw_data_with_retry('AAPL', data) # Calls function to store data in S3. Returns the S3 key where the data was saved
        
        # Verify key format
        assert s3_key.startswith('raw-data/AAPL/')
        assert s3_key.endswith('.json')
        
        # Verify data was stored
        response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key) # Reads the file back from mock S3 
        stored_data = json.loads(response['Body'].read()) # Parse JSON content to prove the data made it to S3
        
        assert len(stored_data) == 2 # Verifies that 2 pieces of data was uploaded to S3
        assert stored_data[0]['close'] == 150.0 
    
    def test_store_raw_data_with_large_dataset(self):
        """Test storage of large dataset."""
        data = [
            {'date': f'2026-01-{i:02d}', 'close': 150.0 + i, 'volume': 50000000}
            for i in range(1, 31)
        ]
        
        s3_key = store_raw_data_with_retry('AAPL', data) # Uploads all 30 records to mock S3 
        
        # Verify data was stored
        response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
        stored_data = json.loads(response['Body'].read())
        
        assert len(stored_data) == 30 # Confirms all 30 records were stored 


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
                {'AttributeName': 'ticker', 'KeyType': 'HASH'}, # Partition key
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'} # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'ticker', 'AttributeType': 'S'}, # String
                {'AttributeName': 'timestamp', 'AttributeType': 'S'} # String
            ],
            BillingMode='PAY_PER_REQUEST' # On-demand billing - like prod
        )
    
    def test_store_anomaly_in_dynamodb(self):
        """Test storing anomaly in DynamoDB."""
        from decimal import Decimal
        anomaly = {
            'ticker': 'AAPL',
            'timestamp': datetime.utcnow().isoformat(),
            'date': '2026-01-21',
            'anomaly_type': 'price',
            'value': Decimal('160.0'),
            'baseline_mean': Decimal('150.0'),
            'baseline_std': Decimal('2.0'),
            'z_score': Decimal('5.0'),
            'threshold': Decimal('2.0'),
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
        
        assert 'Item' in response # Verifies that the record exists in the table
        assert response['Item']['anomaly_type'] == 'price'
        assert float(response['Item']['value']) == 160.0
    
    def test_query_anomalies_by_ticker(self):
        """Test querying anomalies by ticker."""
        from decimal import Decimal
        # Store multiple anomalies
        for i in range(3):
            anomaly = {
                'ticker': 'AAPL',
                'timestamp': f'2026-01-{i+1:02d}T10:00:00',
                'date': f'2026-01-{i+1:02d}',
                'anomaly_type': 'price',
                'value': Decimal(str(160.0 + i)),
                'z_score': Decimal('5.0')
            }
            self.table.put_item(Item=anomaly)
        
        # Query by ticker
        response = self.table.query(
            KeyConditionExpression='ticker = :ticker',
            ExpressionAttributeValues={':ticker': 'AAPL'}
        )
        
        assert response['Count'] == 3 # Verifies all 3 anomalies were returned 


@mock_aws
class TestSNSIntegration:
    """Test SNS integration."""
    
    def setup_method(self, method):
        """Set up SNS topic for testing."""
        self.sns = boto3.client('sns', region_name='us-east-1') # Creates SNS client
        
        # Create mock SNS topic
        response = self.sns.create_topic(Name='stock-tracker-alerts')
        self.topic_arn = response['TopicArn']
        os.environ['SNS_TOPIC_ARN'] = self.topic_arn # Sets environment variable
    
    def test_publish_alert_to_sns(self):
        """Test publishing alert to SNS."""
        message = "Test anomaly alert"
        
        response = self.sns.publish(
            TopicArn=self.topic_arn,
            Subject='Test Alert',
            Message=message
        )
        
        assert 'MessageId' in response # Verifies SNS returned a MessageID 
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200 # Verifies the HTTP status code is 200 (success)


if __name__ == '__main__':
    pytest.main([__file__, '-v']) # Allows running this test file directly 
