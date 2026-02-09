import json
import logging
import boto3
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('stock-anomalies')

def lambda_handler(event, context):
    """
    API handler for anomaly queries.
    Supports:
    - GET /anomalies - List recent anomalies
    - GET /anomalies/{ticker} - Get ticker-specific anomalies
    - GET /health - Health check
    """
    try:
        http_method = event.get('httpMethod')
        path = event.get('path', '')
        path_parameters = event.get('pathParameters') or {}
        
        logger.info(f"API request: {http_method} {path}")
        
        # Health check endpoint
        if path == '/health':
            return response(200, {
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'service': 'stock-anomaly-api'
            })
        
        # List all recent anomalies
        if path == '/anomalies' and http_method == 'GET':
            return list_anomalies()
        
        # Get anomalies for specific ticker
        if path.startswith('/anomalies/') and http_method == 'GET':
            ticker = path_parameters.get('ticker')
            if ticker:
                return get_ticker_anomalies(ticker)
        
        # Unknown endpoint
        return response(404, {'error': 'Endpoint not found'})
        
    except Exception as e:
        logger.error(f"API error: {str(e)}", exc_info=True)
        return response(500, {'error': 'Internal server error'})

def list_anomalies():
    """List recent anomalies (last 7 days)."""
    try:
        # For now, return empty list (will populate in Week 7)
        # In production, would scan table with date filter
        return response(200, {
            'anomalies': [],
            'count': 0,
            'message': 'No anomalies detected yet'
        })
    except Exception as e:
        logger.error(f"Error listing anomalies: {str(e)}")
        return response(500, {'error': 'Failed to list anomalies'})

def get_ticker_anomalies(ticker):
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
        logger.error(f"Error getting ticker anomalies: {str(e)}")
        return response(500, {'error': f'Failed to get anomalies for {ticker}'})

def response(status_code, body):
    """Format API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(body)
    }
