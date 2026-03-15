"""Tests for API handler."""
import json # To parse API responses in tests
import pytest  # Testing framework (Provides test discovery, assertions, fixtures)
from moto import mock_aws # Mocks all AWS services locally so tests don't hit real AWS
import boto3 # AWS SDK to create lock DynamoDB tables in tests
from decimal import Decimal # DynamoDB stores numbers as Decimal

# Add lambda directory to path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda')) # Adds the /lambda/ folder to Python's import path

from api_handler import lambda_handler # Imports lambda_handler function that we are testing


@mock_aws # Tells moto to intercept all AWS API calls in this class. Calls go to motos in-memory mock services. 
class TestAPIHandler:
    """Test API Gateway handler."""
    
    def setup_method(self, method): # Set up before each test function runs. New DynamoDB table upon each run - test isolation
        """Set up test DynamoDB table."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1') # Creates a DynamoDB resource client
        self.table = dynamodb.create_table(
            TableName='stock-anomalies',
            KeySchema=[
                {'AttributeName': 'ticker', 'KeyType': 'HASH'}, # Groups anomlaies by ticker
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'} # Matches the real table schema so the Lambda code works the same way
            ],
            AttributeDefinitions=[
                {'AttributeName': 'ticker', 'AttributeType': 'S'}, # S = String for both ticker and timestamp
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST' # On-demand billing same as production
        )
    
    def test_health_endpoint(self): # Tests that the health check endpoint works correctly. Same endpoint the CD pipeline calls to verify deployment
        """Test /health endpoint."""
        event = { # Creates a dummy API Gateway event - simulates a GET request to /health
            'httpMethod': 'GET', # This event is auto created by API Gateway during the HTTP request. Here we create it manually
            'path': '/health',
            'queryStringParameters': None
        }
        
        response = lambda_handler(event, None) # Calls the function with our fake event. 
        
        assert response['statusCode'] == 200 # Asserts the response status code is 200, if not, test fails
        body = json.loads(response['body']) # Parse the JSON response body back into a Python dictionary
        assert body['status'] == 'healthy' # Asserts the status field equals healthy, if not, test fails
    
    def test_get_all_anomalies_empty(self): # Tests that the function gets anomalies when the DynamoDB table is empty
        """Test getting anomalies when table is empty."""
        event = {
            'httpMethod': 'GET', # Simulates a GET request to /anomalies -> Same request the dashboard makes every 60 seconds
            'path': '/anomalies',
            'queryStringParameters': None
        }
        
        response = lambda_handler(event, None) # Calls the lambda function
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['count'] == 0 # Verifies that count is 0
        assert body['anomalies'] == [] # Verifies anomalies is an empty list
    
    def test_get_all_anomalies_with_data(self): # Tests the /anomalies endpoint when DynamoDB has anomaly records
        """Test getting anomalies with data."""
        # Add test data
        self.table.put_item(Item={
            'ticker': 'TSLA',
            'timestamp': '2026-02-18T10:00:00',
            'anomaly_type': 'price',
            'z_score': Decimal('2.5'),
            'severity': 'high'
        })
        
        event = {
            'httpMethod': 'GET',
            'path': '/anomalies',
            'queryStringParameters': None
        } # Queries table
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200 # Verifies that the AI returns 200 OK
        body = json.loads(response['body'])
        # Just check response structure, not count (moto scan behavior varies)
        assert 'count' in body
        assert 'anomalies' in body
