import json
import logging
import os
import boto3
from datetime import datetime, timedelta
import urllib3
from statistics import mean, stdev
import time

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
ssm = boto3.client('ssm')
s3 = boto3.client('s3')
sns = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')
anomalies_table = dynamodb.Table('stock-anomalies')

# HTTP client
http = urllib3.PoolManager()

# Circuit breaker state
circuit_breaker = {
    'failures': 0,
    'last_failure_time': None,
    'state': 'closed'  # closed, open, half_open
}

def lambda_handler(event, context):
    """
    Stock scanner Lambda function with error handling.
    Fetches stock data, detects anomalies, and stores results.
    """
    try:
        logger.info("Stock scanner started", extra={
            "timestamp": datetime.utcnow().isoformat(),
            "event": event
        })
        
        # Get configuration from Parameter Store with retry
        ticker = get_parameter_with_retry('/stock-tracker/ticker', 'AAPL')
        threshold = float(get_parameter_with_retry('/stock-tracker/anomaly-threshold', '2.0'))
        
        logger.info(f"Configuration: ticker={ticker}, threshold={threshold}")
        
        # Fetch stock data with circuit breaker
        stock_data = fetch_with_circuit_breaker(ticker, days=30)
        
        if not stock_data or len(stock_data) < 20:
            logger.warning(f"Insufficient data for {ticker}")
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'insufficient_data', 'ticker': ticker})
            }
        
        # Store raw data in S3 with retry
        s3_key = store_raw_data_with_retry(ticker, stock_data)
        
        # Detect anomalies
        anomalies = detect_anomalies(ticker, stock_data, threshold)
        
        # Store anomalies and send alerts with error handling
        if anomalies:
            store_anomalies_with_retry(anomalies)
            send_alert_with_retry(anomalies)
        
        # Prepare scan result
        scan_result = {
            "status": "success",
            "result_message": "Stock data collected successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "ticker": ticker,
            "threshold": threshold,
            "data_points": len(stock_data),
            "s3_key": s3_key,
            "anomalies_detected": len(anomalies),
            "latest_price": stock_data[-1]['close'] if stock_data else None,
            "latest_volume": stock_data[-1]['volume'] if stock_data else None
        }
        
        logger.info("Stock scanner completed successfully")
        logger.info(f"Collected {len(stock_data)} data points, detected {len(anomalies)} anomalies")
        
        return {
            'statusCode': 200,
            'body': json.dumps(scan_result)
        }
        
    except Exception as e:
        logger.error(f"Stock scanner failed: {str(e)}", exc_info=True)
        # Re-raise to trigger DLQ
        raise

def retry_with_backoff(func, max_retries=3, initial_delay=1):
    """
    Retry function with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Max retries reached for {func.__name__}: {str(e)}")
                raise
            
            delay = initial_delay * (2 ** attempt)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {str(e)}")
            time.sleep(delay)

def fetch_with_circuit_breaker(ticker, days=30):
    """
    Fetch data with circuit breaker pattern.
    """
    global circuit_breaker
    
    # Check circuit breaker state
    if circuit_breaker['state'] == 'open':
        # Check if enough time has passed to try again
        if circuit_breaker['last_failure_time']:
            time_since_failure = (datetime.utcnow() - circuit_breaker['last_failure_time']).seconds
            if time_since_failure < 60:  # Wait 60 seconds before retry
                logger.warning("Circuit breaker is OPEN, skipping data fetch")
                return None
            else:
                circuit_breaker['state'] = 'half_open'
                logger.info("Circuit breaker moving to HALF_OPEN")
    
    try:
        data = fetch_stock_data_simple(ticker, days)
        
        # Success - reset circuit breaker
        if circuit_breaker['state'] == 'half_open':
            circuit_breaker['state'] = 'closed'
            circuit_breaker['failures'] = 0
            logger.info("Circuit breaker CLOSED")
        
        return data
        
    except Exception as e:
        # Failure - update circuit breaker
        circuit_breaker['failures'] += 1
        circuit_breaker['last_failure_time'] = datetime.utcnow()
        
        if circuit_breaker['failures'] >= 3:
            circuit_breaker['state'] = 'open'
            logger.error("Circuit breaker OPENED after 3 failures")
        
        raise

def get_parameter_with_retry(name, default):
    """Get parameter from Parameter Store with retry logic."""
    def fetch():
        try:
            response = ssm.get_parameter(Name=name)
            return response['Parameter']['Value']
        except Exception as e:
            logger.warning(f"Failed to get parameter {name}: {str(e)}")
            raise
    
    try:
        return retry_with_backoff(fetch, max_retries=3)
    except Exception:
        logger.warning(f"Using default value for {name}: {default}")
        return default

def store_raw_data_with_retry(ticker, data):
    """Store raw stock data in S3 with retry logic."""
    def store():
        bucket_name = os.environ.get('S3_BUCKET', 'stock-scan-data-529088281783')
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        s3_key = f"raw-data/{ticker}/{timestamp}.json"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Stored raw data in S3: s3://{bucket_name}/{s3_key}")
        return s3_key
    
    return retry_with_backoff(store, max_retries=3)

def store_anomalies_with_retry(anomalies):
    """Store detected anomalies in DynamoDB with retry logic."""
    for anomaly in anomalies:
        def store():
            anomalies_table.put_item(Item=anomaly)
            logger.info(f"Stored {anomaly['anomaly_type']} anomaly for {anomaly['ticker']}")
        
        try:
            retry_with_backoff(store, max_retries=3)
        except Exception as e:
            logger.error(f"Failed to store anomaly after retries: {str(e)}")

def send_alert_with_retry(anomalies):
    """Send SNS alert with retry logic."""
    sns_topic_arn = os.environ.get('SNS_TOPIC_ARN', 
        'arn:aws:sns:us-east-1:529088281783:stock-tracker-alerts')
    
    for anomaly in anomalies:
        def send():
            message = format_alert_message(anomaly)
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"Stock Anomaly Detected: {anomaly['ticker']}",
                Message=message
            )
            logger.info(f"Sent alert for {anomaly['ticker']} {anomaly['anomaly_type']} anomaly")
        
        try:
            retry_with_backoff(send, max_retries=3)
        except Exception as e:
            logger.error(f"Failed to send alert after retries: {str(e)}")

def detect_anomalies(ticker, data, threshold):
    """
    Detect anomalies using Z-score analysis.
    Uses 20-day baseline for comparison.
    """
    try:
        if len(data) < 21:
            logger.warning("Not enough data for anomaly detection (need 21+ days)")
            return []
        
        # Use last 20 days as baseline, current day for detection
        baseline_data = data[-21:-1]  # Days -21 to -2
        current_data = data[-1]  # Most recent day
        
        # Calculate baseline statistics
        baseline_prices = [d['close'] for d in baseline_data]
        baseline_volumes = [d['volume'] for d in baseline_data]
        
        price_mean = mean(baseline_prices)
        price_std = stdev(baseline_prices)
        volume_mean = mean(baseline_volumes)
        volume_std = stdev(baseline_volumes)
        
        # Calculate Z-scores for current day
        price_zscore = (current_data['close'] - price_mean) / price_std if price_std > 0 else 0
        volume_zscore = (current_data['volume'] - volume_mean) / volume_std if volume_std > 0 else 0
        
        logger.info(f"Z-scores - Price: {price_zscore:.2f}, Volume: {volume_zscore:.2f}")
        
        anomalies = []
        
        # Check for price anomaly
        if abs(price_zscore) > threshold:
            anomalies.append({
                'ticker': ticker,
                'timestamp': datetime.utcnow().isoformat(),
                'date': current_data['date'],
                'anomaly_type': 'price',
                'value': current_data['close'],
                'baseline_mean': round(price_mean, 2),
                'baseline_std': round(price_std, 2),
                'z_score': round(price_zscore, 2),
                'threshold': threshold,
                'severity': 'high' if abs(price_zscore) > threshold * 1.5 else 'medium'
            })
        
        # Check for volume anomaly
        if abs(volume_zscore) > threshold:
            anomalies.append({
                'ticker': ticker,
                'timestamp': datetime.utcnow().isoformat(),
                'date': current_data['date'],
                'anomaly_type': 'volume',
                'value': current_data['volume'],
                'baseline_mean': int(volume_mean),
                'baseline_std': int(volume_std),
                'z_score': round(volume_zscore, 2),
                'threshold': threshold,
                'severity': 'high' if abs(volume_zscore) > threshold * 1.5 else 'medium'
            })
        
        if anomalies:
            logger.info(f"Detected {len(anomalies)} anomalies for {ticker}")
        else:
            logger.info(f"No anomalies detected for {ticker}")
        
        return anomalies
        
    except Exception as e:
        logger.error(f"Error detecting anomalies: {str(e)}")
        return []

def store_anomalies(anomalies):
    """Store detected anomalies in DynamoDB."""
    try:
        for anomaly in anomalies:
            anomalies_table.put_item(Item=anomaly)
            logger.info(f"Stored {anomaly['anomaly_type']} anomaly for {anomaly['ticker']}")
    except Exception as e:
        logger.error(f"Error storing anomalies: {str(e)}")

def send_alert(anomalies):
    """Send SNS alert for detected anomalies."""
    try:
        sns_topic_arn = os.environ.get('SNS_TOPIC_ARN', 
            'arn:aws:sns:us-east-1:529088281783:stock-tracker-alerts')
        
        for anomaly in anomalies:
            message = format_alert_message(anomaly)
            
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"Stock Anomaly Detected: {anomaly['ticker']}",
                Message=message
            )
            
            logger.info(f"Sent alert for {anomaly['ticker']} {anomaly['anomaly_type']} anomaly")
            
    except Exception as e:
        logger.error(f"Error sending alert: {str(e)}")

def format_alert_message(anomaly):
    """Format anomaly data into readable alert message."""
    direction = "increased" if anomaly['z_score'] > 0 else "decreased"
    
    message = f"""
🚨 Anomaly Detected for {anomaly['ticker']}

Type: {anomaly['anomaly_type'].upper()}
Severity: {anomaly['severity'].upper()}
Date: {anomaly['date']}

Current Value: {anomaly['value']:,.2f}
Baseline Mean: {anomaly['baseline_mean']:,.2f}
Standard Deviation: {anomaly['baseline_std']:,.2f}

Z-Score: {anomaly['z_score']} (threshold: {anomaly['threshold']})

The {anomaly['anomaly_type']} has {direction} significantly beyond normal levels.
This represents a {abs(anomaly['z_score']):.1f} standard deviation move.
"""
    return message.strip()

def fetch_stock_data_simple(ticker, days=30):
    """
    Fetch stock data using a simple approach.
    For now, generates mock data. In production, integrate with real API.
    """
    try:
        logger.info(f"Generating mock data for {ticker}")
        
        # Generate mock data for last 30 days
        data = []
        base_price = 150.0  # Mock base price for AAPL
        
        for i in range(days):
            date = datetime.now() - timedelta(days=days-i)
            # Simple random walk for mock data
            price_change = (hash(f"{ticker}{date.date()}") % 10 - 5) * 0.5
            price = base_price + price_change
            
            data.append({
                'date': date.strftime('%Y-%m-%d'),
                'open': round(price - 0.5, 2),
                'high': round(price + 1.0, 2),
                'low': round(price - 1.0, 2),
                'close': round(price, 2),
                'volume': (hash(f"{ticker}{date.date()}volume") % 1000000) + 50000000
            })
        
        logger.info(f"Generated {len(data)} mock data points for {ticker}")
        return data
        
    except Exception as e:
        logger.error(f"Error generating data for {ticker}: {str(e)}")
        return None

def store_raw_data(ticker, data):
    """Store raw stock data in S3."""
    try:
        bucket_name = os.environ.get('S3_BUCKET', 'stock-scan-data-529088281783')
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        s3_key = f"raw-data/{ticker}/{timestamp}.json"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Stored raw data in S3: s3://{bucket_name}/{s3_key}")
        return s3_key
        
    except Exception as e:
        logger.error(f"Error storing data in S3: {str(e)}")
        raise

def get_parameter(name, default):
    """Get parameter from Parameter Store with fallback to default."""
    try:
        response = ssm.get_parameter(Name=name)
        return response['Parameter']['Value']
    except Exception as e:
        logger.warning(f"Failed to get parameter {name}: {str(e)}, using default: {default}")
        return default


def detect_anomalies(ticker, data, threshold):
    """
    Detect anomalies using Z-score analysis.
    Uses 20-day baseline for comparison.
    """
    try:
        if len(data) < 21:
            logger.warning("Not enough data for anomaly detection (need 21+ days)")
            return []
        
        # Use last 20 days as baseline, current day for detection
        baseline_data = data[-21:-1]
        current_data = data[-1]
        
        # Calculate baseline statistics
        baseline_prices = [d['close'] for d in baseline_data]
        baseline_volumes = [d['volume'] for d in baseline_data]
        
        price_mean = mean(baseline_prices)
        price_std = stdev(baseline_prices)
        volume_mean = mean(baseline_volumes)
        volume_std = stdev(baseline_volumes)
        
        # Calculate Z-scores
        price_zscore = (current_data['close'] - price_mean) / price_std if price_std > 0 else 0
        volume_zscore = (current_data['volume'] - volume_mean) / volume_std if volume_std > 0 else 0
        
        logger.info(f"Z-scores - Price: {price_zscore:.2f}, Volume: {volume_zscore:.2f}")
        
        anomalies = []
        
        # Check for price anomaly
        if abs(price_zscore) > threshold:
            anomalies.append({
                'ticker': ticker,
                'timestamp': datetime.utcnow().isoformat(),
                'date': current_data['date'],
                'anomaly_type': 'price',
                'value': current_data['close'],
                'baseline_mean': round(price_mean, 2),
                'baseline_std': round(price_std, 2),
                'z_score': round(price_zscore, 2),
                'threshold': threshold,
                'severity': 'high' if abs(price_zscore) > threshold * 1.5 else 'medium'
            })
        
        # Check for volume anomaly
        if abs(volume_zscore) > threshold:
            anomalies.append({
                'ticker': ticker,
                'timestamp': datetime.utcnow().isoformat(),
                'date': current_data['date'],
                'anomaly_type': 'volume',
                'value': current_data['volume'],
                'baseline_mean': int(volume_mean),
                'baseline_std': int(volume_std),
                'z_score': round(volume_zscore, 2),
                'threshold': threshold,
                'severity': 'high' if abs(volume_zscore) > threshold * 1.5 else 'medium'
            })
        
        if anomalies:
            logger.info(f"Detected {len(anomalies)} anomalies for {ticker}")
        else:
            logger.info(f"No anomalies detected for {ticker}")
        
        return anomalies
        
    except Exception as e:
        logger.error(f"Error detecting anomalies: {str(e)}")
        return []

def format_alert_message(anomaly):
    """Format anomaly data into readable alert message."""
    direction = "increased" if anomaly['z_score'] > 0 else "decreased"
    
    message = f"""
🚨 Anomaly Detected for {anomaly['ticker']}

Type: {anomaly['anomaly_type'].upper()}
Severity: {anomaly['severity'].upper()}
Date: {anomaly['date']}

Current Value: {anomaly['value']:,.2f}
Baseline Mean: {anomaly['baseline_mean']:,.2f}
Standard Deviation: {anomaly['baseline_std']:,.2f}

Z-Score: {anomaly['z_score']} (threshold: {anomaly['threshold']})

The {anomaly['anomaly_type']} has {direction} significantly beyond normal levels.
This represents a {abs(anomaly['z_score']):.1f} standard deviation move.
"""
    return message.strip()

def fetch_stock_data_simple(ticker, days=30):
    """
    Fetch stock data using a simple approach.
    For now, generates mock data. In production, integrate with real API.
    """
    try:
        logger.info(f"Generating mock data for {ticker}")
        
        # Generate mock data for last 30 days
        data = []
        base_price = 150.0
        
        for i in range(days):
            date = datetime.now() - timedelta(days=days-i)
            price_change = (hash(f"{ticker}{date.date()}") % 10 - 5) * 0.5
            price = base_price + price_change
            
            data.append({
                'date': date.strftime('%Y-%m-%d'),
                'open': round(price - 0.5, 2),
                'high': round(price + 1.0, 2),
                'low': round(price - 1.0, 2),
                'close': round(price, 2),
                'volume': (hash(f"{ticker}{date.date()}volume") % 1000000) + 50000000
            })
        
        logger.info(f"Generated {len(data)} mock data points for {ticker}")
        return data
        
    except Exception as e:
        logger.error(f"Error generating data for {ticker}: {str(e)}")
        return None
