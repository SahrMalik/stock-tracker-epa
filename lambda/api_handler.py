import json # Converts Python objects to/from JSON for API responses
import logging # Provides structured logging for CloudWatch
import boto3 # AWS SDK for Python - used to interact with AWS services
from datetime import datetime, timedelta # Date handling for time based queries 
from decimal import Decimal # Handles DynamoDB number format
 
logger = logging.getLogger() # Creates a logger instance for this Lambda function
logger.setLevel(logging.INFO) # Sets log level to INFO - logs appear in CloudWatch

dynamodb = boto3.resource('dynamodb') # Creates a DynamoDB resource client 
table = dynamodb.Table('stock-anomalies') # References the DynamoDB table by name 

def lambda_handler(event, context): # Entry point - AWS Lambda calls this function for every API request
    """
    API handler for anomaly queries.
    Supports:
    - GET /anomalies - List recent anomalies
    - GET /anomalies/{ticker} - Get ticker-specific anomalies
    - GET /health - Health check
    """
    try:
        http_method = event.get('httpMethod') # Gets the HTTP method (GET, POST, etc.) from the API Gateway event path 
        path = event.get('path', '') # Gets the URL path
        path_parameters = event.get('pathParameters') or {} # Gets URL parameters 
        
        logger.info(f"API request: {http_method} {path}") # Logs the request to CloudWatch
        
        # Health check endpoint
        if path == '/health':
            return response(200, { # returns a 200 status if the API is running
                'status': 'healthy', 
                'timestamp': datetime.utcnow().isoformat(),
                'service': 'stock-anomaly-api'
            }) # The CD pipeline calls this after deployment to verify everything is working
        
        # List all recent anomalies
        if path == '/anomalies' and http_method == 'GET': # Returns all recent anomalies from DynamoDB
            return list_anomalies() # This is what the dashboard calls every 60 seconds to refresh data
        
        # Get anomalies for specific ticker
        if path.startswith('/anomalies/') and http_method == 'GET': # Extracts the ticker symbol from the URL path parameters
            ticker = path_parameters.get('ticker') 
            if ticker:
                return get_ticker_anomalies(ticker) # queries DynamoDB table filtered by ticker
        
        # Unknown endpoint
        return response(404, {'error': 'Endpoint not found'}) # If no route matched, returns a 404
        
    except Exception as e:
        logger.error(f"API error: {str(e)}", exc_info=True)
        return response(500, {'error': 'Internal server error'}) # Logs the full error message to CloudWatch

def list_anomalies(): # Called when the dashboard or user hits GET /anomalies
    """List recent anomalies (last 7 days)."""
    try:
        # Scan table for all anomalies (limit to recent ones)
        response_data = table.scan(Limit=100) # Returns up to 100 items from table
        items = response_data.get('Items', []) # Extracts the list of anomaly records from the DynamoDB response. Returns empty list if no items found. 
        
        # Convert Decimal to float for JSON serialization. DynamoDB stores numbers as Decimal type, but JSON does not. 
        anomalies = []
        for item in items:
            anomaly = {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()} # Loops through each anomaly record and converts Decimal to float
            anomalies.append(anomaly)
        
        # Sort by timestamp descending (most recent first)
        anomalies.sort(key=lambda x: x.get('timestamp', ''), reverse=True) # Sorts anomalies by timestamp in descending order. This is what the Dashboard displays
        
        return response(200, {
            'anomalies': anomalies,
            'count': len(anomalies),
            'message': f'Found {len(anomalies)} anomalies' if anomalies else 'No anomalies detected yet'
        }) # This JSON is what the dashboard receives and renders in the table
    except Exception as e:
        logger.error(f"Error listing anomalies: {str(e)}") # Logs the error to CloudWatch for debugging 
        return response(500, {'error': 'Failed to list anomalies'})

def get_ticker_anomalies(ticker): # Function that retrieves anomalies for a specific ticker. Called when user hits GET /anomalies/{ticker}
    """Get anomalies for specific ticker."""
    try:
        # Query DynamoDB by ticker
        result = table.query(
            KeyConditionExpression='ticker = :ticker',
            ExpressionAttributeValues={':ticker': ticker.upper()},
            Limit=50
        )
        
        return response(200, {
            'ticker': ticker.upper(),
            'anomalies': result.get('Items', []),
            'count': len(result.get('Items', []))
        })
    except Exception as e:
        logger.error(f"Error getting ticker anomalies: {str(e)}") # Logs error to CloudWatch
        return response(500, {'error': f'Failed to get anomalies for {ticker}'})

def response(status_code, body):
    """Format API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json', # Tells browser that the response is JSON
            'Access-Control-Allow-Origin': '*', # CORS header that allows any website to call this API. This is required because the dashboard is a different origin than the API Gateway domain
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS' # Only GET and OPTIONS are permitted
        },
        'body': json.dumps(body) # Converts the Python dictionary to a JSON string. It's what API Gateway requires
    }
