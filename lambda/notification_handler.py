import json
import logging
import os
import urllib3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

http = urllib3.PoolManager()

def lambda_handler(event, context):
    """
    SNS to Slack notification handler.
    Receives SNS messages and forwards to Slack webhook.
    """
    try:
        # Get Slack webhook URL from environment variable
        slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL', '')
        
        if not slack_webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not configured, skipping notification")
            return {'statusCode': 200, 'body': 'Webhook not configured'}
        
        # Parse SNS message
        for record in event.get('Records', []):
            sns_message = record.get('Sns', {})
            subject = sns_message.get('Subject', 'Stock Tracker Alert')
            message = sns_message.get('Message', '')
            
            logger.info(f"Processing SNS message: {subject}")
            
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
                'POST',
                slack_webhook_url,
                body=json.dumps(slack_message).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status == 200:
                logger.info("Slack notification sent successfully")
            else:
                logger.error(f"Slack notification failed: {response.status}")
        
        return {'statusCode': 200, 'body': 'Notifications processed'}
        
    except Exception as e:
        logger.error(f"Notification handler error: {str(e)}", exc_info=True)
        return {'statusCode': 500, 'body': 'Error processing notifications'}
