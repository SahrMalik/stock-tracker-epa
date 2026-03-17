import json # Parse and create JSON data (API responses, S3 storage)
import logging # Structured logging to CloudWatch
import os # Read environment variables (like S3_BUCKET)
import boto3 # AWS SDK for Python (talks to DynamoDB, S3, SNS, Parameter Store)
from datetime import datetime, timedelta # Date/time handling (calculate 30-day range, timestamps)
import urllib3 # HTTP client (used for Slack webhook calls)
from statistics import mean, stdev # Statistical functions for Z-score calculation
import time
import yfinance as yf # Yahoo Finance library (fetches real ticker data)
from decimal import Decimal # Handles DynamoDB number format (uses Decimal instead of Float)

# Configure structured logging
logger = logging.getLogger() # Gets root logger
logger.setLevel(logging.INFO) # Logs everything at INFO level and above (INFO, WARNING, ERROR)

# AWS clients - Creates AWS service connections that the Lambda uses:
ssm = boto3.client('ssm') # Parameter store client (reads ticker, threshold config)
s3 = boto3.client('s3') # Uploads raw scan data
sns = boto3.client('sns') # Publishes anomaly alerts
dynamodb = boto3.resource('dynamodb')
anomalies_table = dynamodb.Table('stock-anomalies')

# HTTP client
http = urllib3.PoolManager() # Manages HTTP connections efficiently, reusing them across multiple requests

# Circuit breaker state
circuit_breaker = {
    'failures': 0,
    'last_failure_time': None,
    'state': 'closed'  # closed, open, half_open
} # System starts as closed. If 3 consecutive failures -> switches to open - stops calling Yahoo Finance. Switches to hald open after 60 seconds

def lambda_handler(event, context): # Event - Data from EventBridge (trigger info). Context - Lambda metadata (request ID, time remaining)
    """
    Stock scanner Lambda function with error handling.
    Fetches stock data, detects anomalies, and stores results.
    """
    try:
        logger.info("Stock scanner started", extra={
            "timestamp": datetime.utcnow().isoformat(),
            "event": event
        }) # Logs the start of execution with current UTC timestamp and triggger event to CloudWatch
        
        # Get configuration from Parameter Store with retry
        ticker = get_parameter_with_retry('/stock-tracker/ticker', 'AMZN') # Reads the stock ticker from Parameter store. Falls back to AMZN if Parameter store is unreachable
        threshold = float(get_parameter_with_retry('/stock-tracker/anomaly-threshold', '2.0')) # Reads the Z-score threshold from Parameter Store. Converts string to float. Falls back to 2.0
        
        logger.info(f"Configuration: ticker={ticker}, threshold={threshold}") # Logs the loaded config for debugging
        
        # Fetch stock data with circuit breaker
        stock_data = fetch_with_circuit_breaker(ticker, days=30) # Fetches 30 days of real stock data from Yahoo Finance, protected by circuit breaker pattern
        
        if not stock_data or len(stock_data) < 20: # Checks if data was returned and has at least 20 points (needed for 20-day base calculation)
            logger.warning(f"Insufficient data for {ticker}") # Logs a warning if not enough data
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'insufficient_data', 'ticker': ticker})
            } # Retruns early with a 200 status. Prevents the function from crashing on bad data
        
        # Store raw data in S3 with retry
        s3_key = store_raw_data_with_retry(ticker, stock_data) # Uploads the raw stock data (all 30 days) as JSON to S3. Uses retry logic in case S3 is temporarily unavailable.
        
        # Detect anomalies
        anomalies = detect_anomalies(ticker, stock_data, threshold) # Runs Z-score analysis on the data. Compares the most recent day against the 20-day baseline. Returns a list of anomalies
        
        # Store anomalies and send alerts with error handling
        if anomalies: 
            store_anomalies_with_retry(anomalies) # Writes each anomaly record to DynamoDB (ticker, timestamp, z-score, severity) Uses retry logic in case DynamoDB is unavailable
            send_alert_with_retry(anomalies) # Publishes anomaly details to the SNS topic, which triggers the notification Lambda -> Slack alert
        
        # Prepare scan result
        scan_result = {
            "status": "success",
            "result_message": "Stock data collected successfully",
            "timestamp": datetime.utcnow().isoformat(), # When the scan completed in UTC time
            "ticker": ticker, # Which stock was scanned
            "threshold": threshold, # What Z-score threshold was used
            "data_points": len(stock_data), # How many days of data was used
            "s3_key": s3_key, # Where the raw data was stored
            "anomalies_detected": len(anomalies), # How many anomalies were found
            "latest_price": stock_data[-1]['close'] if stock_data else None, # Most recent closing price
            "latest_volume": stock_data[-1]['volume'] if stock_data else None # Most recent trading volume
        }
        
        logger.info("Stock scanner completed successfully") # Logs successful completion to CloudWatch
        logger.info(f"Collected {len(stock_data)} data points, detected {len(anomalies)} anomalies") # Logs a summary of what happened: e.g. "Collected 27 data points, detected 0 anomalies"
        
        return {
            'statusCode': 200,
            'body': json.dumps(scan_result) # Converts the Python dictionary to a JSON string
        } # Returns the scan result as an HTTP style response. 200 means success
        
    except Exception as e:
        logger.error(f"Stock scanner failed: {str(e)}", exc_info=True) # Logs the error to CloudWatch, includes full stack trace, which line failed and why
        # Re-raise to trigger DLQ
        raise # retires 2 times, as configured in CDK. Sends to DLQ after failed retries

def retry_with_backoff(func, max_retries=3, initial_delay=1): # Reusable retry function. Takes any function, retries it up to 3 times with increasing dealys
    """
    Retry function with exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            return func() # Tries to execute the function
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Max retries reached for {func.__name__}: {str(e)}") # If all retries exhausted, logs the error and gives up
                raise
            
            delay = initial_delay * (2 ** attempt)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {str(e)}") # Logs the retry attempt with delay time and error message to CloudWatch
            time.sleep(delay)

def fetch_with_circuit_breaker(ticker, days=30): # Fetch Yahoo Finance data with circuit breaker logic
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

def get_parameter_with_retry(name, default): # Reads a value from Parameter Store with retry logic
    """Get parameter from Parameter Store with retry logic."""
    def fetch():
        try:
            response = ssm.get_parameter(Name=name)
            return response['Parameter']['Value'] # Calls AWS parameter store and extracts the value (e.g. TSLA or 2.0)
        except Exception as e:
            logger.warning(f"Failed to get parameter {name}: {str(e)}") 
            raise # If the call fails, logs a warning and re-raises so retry_with_backoff can retry it
    
    try:
        return retry_with_backoff(fetch, max_retries=3)
    except Exception:
        logger.warning(f"Using default value for {name}: {default}")
        return default # If all retries fail, falls back to the default value instead of crashing. So if Parameter Store is down, scanner still runs with ticker=TSLA and threshold=2.0

def store_raw_data_with_retry(ticker, data): # Uploads raw scan data to S3
    """Store raw stock data in S3 with retry logic."""
    def store():
        bucket_name = os.environ.get('S3_BUCKET', 'stock-scan-data-529088281783') # Gets the S3 bucket name from the environment variable (set in CDK). Falls back to hardcoded name if not set
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S') # Creates a timestamp string for unique file naming
        s3_key = f"raw-data/{ticker}/{timestamp}.json" # Builds the file path organised by ticker and timestamp so each scan has a unique file
        
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        ) # Uploads data to S3. Convers the Python list formatted to JSON. 
        
        logger.info(f"Stored raw data in S3: s3://{bucket_name}/{s3_key}") # Logs the S3 location for debugging
        return s3_key # Returns the file path so it can be included in the scan result
    
    return retry_with_backoff(store, max_retries=3) # Wraps whole function in retry logic

def store_anomalies_with_retry(anomalies): # Sends detected anomalies to DynamoDB with rery logic
    """Store detected anomalies in DynamoDB with retry logic."""
    for anomaly in anomalies: # Loops through each anomaly
        def store():
            # Convert float values to Decimal for DynamoDB
            item = {k: Decimal(str(v)) if isinstance(v, float) else v for k, v in anomaly.items()}
            anomalies_table.put_item(Item=item)
            logger.info(f"Stored {anomaly['anomaly_type']} anomaly for {anomaly['ticker']}")
        
        try:
            retry_with_backoff(store, max_retries=3)
        except Exception as e:
            logger.error(f"Failed to store anomaly after retries: {str(e)}")

def send_alert_with_retry(anomalies): # Sends SNS alert
    """Send SNS alert with retry logic."""
    sns_topic_arn = os.environ.get('SNS_TOPIC_ARN', 
        'arn:aws:sns:us-east-1:529088281783:stock-tracker-alerts') # Gets the SNS topic ARN from environment variable. Falls back to hardcoded if not set
    
    for anomaly in anomalies: # Loops through each anomaly, sedning a seperate alert for each
        def send():
            message = format_alert_message(anomaly) # creates a human-readable alert message 
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f"Stock Anomaly Detected: {anomaly['ticker']}",
                Message=message
            ) # Publishes to SNS
            logger.info(f"Sent alert for {anomaly['ticker']} {anomaly['anomaly_type']} anomaly") # Logs which alert was sent
        
        try:
            retry_with_backoff(send, max_retries=3)
        except Exception as e:
            logger.error(f"Failed to send alert after retries: {str(e)}")

def detect_anomalies(ticker, data, threshold): # Detect anomalies using Z-score analysis
    """
    Detect anomalies using Z-score analysis.
    Uses 20-day baseline for comparison.
    """
    try:
        if len(data) < 21:
            logger.warning("Not enough data for anomaly detection (need 21+ days)")
            return [] # Needs at least 21 days: 20 for baseline + 1 for the current day to compare
        
        # Use last 20 days as baseline, current day for detection
        baseline_data = data[-21:-1]  # Days -21 to -2
        current_data = data[-1]  # Most recent day
        
        # Calculate baseline statistics
        baseline_prices = [d['close'] for d in baseline_data] # Extracts just the closing prices from the 20 baseline days into a list
        baseline_volumes = [d['volume'] for d in baseline_data] # Same for volumes
        
        price_mean = mean(baseline_prices) # Avg closing price over 20 days
        price_std = stdev(baseline_prices) # Standard deviation
        volume_mean = mean(baseline_volumes)
        volume_std = stdev(baseline_volumes)
        
        # Calculate Z-scores for current day
        price_zscore = (current_data['close'] - price_mean) / price_std if price_std > 0 else 0
        volume_zscore = (current_data['volume'] - volume_mean) / volume_std if volume_std > 0 else 0
        
        logger.info(f"Z-scores - Price: {price_zscore:.2f}, Volume: {volume_zscore:.2f}") # Logs both Z-scores
        
        anomalies = [] # Anomalies list to be populated:
        
        # Check for price anomaly
        if abs(price_zscore) > threshold:
            anomalies.append({ # Adds price anomaly record to the list
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
            logger.info(f"Detected {len(anomalies)} anomalies for {ticker}") # Logs result
        else:
            logger.info(f"No anomalies detected for {ticker}")
        
        return anomalies # Returns list
        
    except Exception as e:
        logger.error(f"Error detecting anomalies: {str(e)}") # Logs error
        return [] # Returns empty list instead of crashing

def format_alert_message(anomaly): # Formats anomaly into a human-readable message for Slack/SNS alerts
    """Format anomaly data into readable alert message."""
    direction = "increased" if anomaly['z_score'] > 0 else "decreased" # Determines if value went up or down
    
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

def fetch_stock_data_simple(ticker, days=30): # Fetches real stock data from Yahoo Finance
    """
    Fetch real stock data from Yahoo Finance.
    """
    try:
        logger.info(f"Fetching real data for {ticker} from Yahoo Finance") # Logs start of data fetch to CloudWatch
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10)  # Extra days to account for weekends
        
        # Fetch data using yfinance
        stock = yf.Ticker(ticker) # Creates a Yahoo Finance ticker obkect 
        hist = stock.history(start=start_date.strftime('%Y-%m-%d'), #Fetches historical daily data between the start and end dates. Returns a pandas dataframe
                            end=end_date.strftime('%Y-%m-%d'))
        
        if hist.empty:
            logger.error(f"No data returned for {ticker}")
            return None # If Yahoo Finance returns nothing, logs error and returns none
        
        # Convert to our format
        data = [] # Empty list to store converted data
        for date, row in hist.iterrows(): # Loops through each row of the pandas dataframe. date is the trading date, row contains the proce/volume data
            data.append({
                'date': date.strftime('%Y-%m-%d'), # Converts date to a string format like 2026-03-03
                'open': round(float(row['Open']), 2),
                'high': round(float(row['High']), 2),
                'low': round(float(row['Low']), 2),
                'close': round(float(row['Close']), 2), # Extracts rach price, converts from pandas type to Python float, rounds to 2 decimal places
                'volume': int(row['Volume']) # Converts volume to integer 
            })
        
        # Get last N days
        data = data[-days:]
        
        logger.info(f"Fetched {len(data)} real data points for {ticker}") # Logs how many days were fetched
        return data
        
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {str(e)}") # If Yahoo Finance fails, logs the error and returns None instead of crashing
        return None




