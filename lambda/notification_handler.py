import json # Converts Python objects to/from JSON for Slack message formatting
import logging # Structured logging for CloudWatch
import os # Access environment variables
import urllib3 # HTTP client library to send POST requests to Slack webhook
import boto3 # AWS SDK to read Slack webhook URL from Parameter Store

logger = logging.getLogger() 
logger.setLevel(logging.INFO) # Creates a logger instance and sets level to INFO

http = urllib3.PoolManager() # Creates HTTP connection pool manager. Used to send HTTP POST requests to the Slack webhook URL
ssm = boto3.client('ssm') # Creates a AWS SSM client. Used to securely retrieve the Slack webhook URL from Parameter Store

def lambda_handler(event, context): # Triggered by SNS when an anomaly is detected
    """
    SNS to Slack notification handler.
    Receives SNS messages and forwards to Slack webhook.
    """
    try:
        # Get Slack webhook URL from Parameter Store
        try:
            response = ssm.get_parameter(Name='/stock-tracker/slack-webhook', WithDecryption=True) 
            slack_webhook_url = response['Parameter']['Value'] # Retrieves the Slack webhook URL from AWS Parameter Store
        except Exception as e:
            logger.warning(f"Failed to get Slack webhook from Parameter Store: {str(e)}") # Logs a warning to CloudWatch but doesn't crash the Lambda
            return {'statusCode': 200, 'body': 'Webhook not configured'}
        
        if not slack_webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not configured, skipping notification") # If parameter is empty, logs warning and exits
            return {'statusCode': 200, 'body': 'Webhook not configured'}
        
        # Parse SNS message
        for record in event.get('Records', []): # Theoretically can be multiple SNS messages in one event, so we loop through each record
            sns_message = record.get('Sns', {}) # In practice, there's usually just one record per invocation
            subject = sns_message.get('Subject', 'Stock Tracker Alert')
            message = sns_message.get('Message', '') # Extracts the SNS message details from the record
            
            logger.info(f"Processing SNS message: {subject}") # Logs which alert is being processed to CloudWatch 
            
            # Format Slack message
            slack_message = {
                'text': f"*{subject}*",
                'blocks': [
                    {
                        'type': 'header',
                        'text': {
                            'type': 'plain_text',
                            'text': subject
                        }
                    },
                    {
                        'type': 'section',
                        'text': {
                            'type': 'mrkdwn',
                            'text': message
                        }
                    },
                    {
                        'type': 'context',
                        'elements': [
                            {
                                'type': 'mrkdwn',
                                'text': f"Timestamp: {sns_message.get('Timestamp', 'N/A')}"
                            }
                        ]
                    }
                ]
            }
            
            # Send to Slack
            response = http.request(
                'POST', # Sends HTTP POST request to the Slack webhook URL
                slack_webhook_url,
                body=json.dumps(slack_message).encode('utf-8'), # Converts the slack_message dictionary to a JSON string
                headers={'Content-Type': 'application/json'} 
            )
            
            if response.status == 200: # Checks if Slack accepted the message
                logger.info("Slack notification sent successfully")
            else:
                logger.error(f"Slack notification failed: {response.status}")
        
        return {'statusCode': 200, 'body': 'Notifications processed'} # Tells SNS the message was handled successfully 
        
    except Exception as e: # Catches any unexpected errors in the entire function
        logger.error(f"Notification handler error: {str(e)}", exc_info=True)
        return {'statusCode': 500, 'body': 'Error processing notifications'}
