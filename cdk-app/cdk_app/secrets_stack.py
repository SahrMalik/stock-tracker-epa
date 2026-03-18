from aws_cdk import (
    Stack,
    aws_secretsmanager as secretsmanager, # For highly sensitive secrets like database passwords, API keys
    aws_ssm as ssm, # AWS Systems Manager Parameter Store for config values and less sensitive secrets
)
from constructs import Construct
import json # For json formatting of secret values

class SecretsStack(Stack): # Third stack to be deployed
    """
    CDK Stack for secrets and configuration management.
    Week 5 Day 2: Secrets Manager and Parameter Store.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Secrets Manager: Store API credentials
        # Placeholder secret - will be updated manually with real API key
        self.api_secret = secretsmanager.Secret(
            self, "StockAPISecret",
            secret_name="stock-api-credentials", # Name in AWS console 
            description="API credentials for stock data provider",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({ # JSON template with placeholder values
                    "api_provider": "placeholder",
                    "api_key": "placeholder-key"
                }),
                generate_string_key="api_key", # Secrets Manager auto-generates a random secure string for the api_key field 
            ),
        )

        # Parameter Store: Stock ticker configuration
        self.ticker_param = ssm.StringParameter(
            self, "TickerParameter",
            parameter_name="/stock-tracker/ticker", # The path in parameter store
            string_value="AMZN", # Default value set in CDK 
            description="Stock ticker to monitor",
        )

        # Parameter Store: Anomaly detection thresholds
        self.threshold_param = ssm.StringParameter(
            self, "ThresholdParameter",
            parameter_name="/stock-tracker/anomaly-threshold", # Path in parameter store
            string_value="2.0",  # Z-score threshold
            description="Z-score threshold for anomaly detection",
        )

        # Parameter Store: Market hours configuration
        self.market_hours_param = ssm.StringParameter(
            self, "MarketHoursParameter",
            parameter_name="/stock-tracker/market-hours", # Path in parameter store
            string_value=json.dumps({ # Stores a JSON object as a string containing:
                "open": "09:30",
                "close": "16:00",
                "timezone": "America/New_York"
            }),
            description="Market hours configuration",
        )

        # Parameter Store: Alert configuration
        self.alert_config_param = ssm.StringParameter(
            self, "AlertConfigParameter",
            parameter_name="/stock-tracker/alert-config",
            string_value=json.dumps({
                "enabled": True, # Alerts are turned on. Set to False to silence all alerts without removing any infrastructure
                "min_severity": "high" # Only send alerts for HIGH severity anomalies
            }),
            description="Alert configuration settings",
        )
