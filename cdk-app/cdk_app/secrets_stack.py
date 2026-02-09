from aws_cdk import (
    Stack,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
)
from constructs import Construct
import json

class SecretsStack(Stack):
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
            secret_name="stock-api-credentials",
            description="API credentials for stock data provider",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({
                    "api_provider": "placeholder",
                    "api_key": "placeholder-key"
                }),
                generate_string_key="api_key",
            ),
        )

        # Parameter Store: Stock ticker configuration
        self.ticker_param = ssm.StringParameter(
            self, "TickerParameter",
            parameter_name="/stock-tracker/ticker",
            string_value="AAPL",
            description="Stock ticker to monitor",
        )

        # Parameter Store: Anomaly detection thresholds
        self.threshold_param = ssm.StringParameter(
            self, "ThresholdParameter",
            parameter_name="/stock-tracker/anomaly-threshold",
            string_value="2.0",  # Z-score threshold
            description="Z-score threshold for anomaly detection",
        )

        # Parameter Store: Market hours configuration
        self.market_hours_param = ssm.StringParameter(
            self, "MarketHoursParameter",
            parameter_name="/stock-tracker/market-hours",
            string_value=json.dumps({
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
                "enabled": True,
                "min_severity": "high"
            }),
            description="Alert configuration settings",
        )
