from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct

class ApiStack(Stack):
    """
    CDK Stack for API Gateway.
    Week 6 Day 1: REST API for anomaly queries.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Lambda function for API handling
        api_handler = _lambda.Function(
            self, "ApiHandler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="api_handler.lambda_handler",
            code=_lambda.Code.from_asset("../lambda"),
            function_name="stock-api-handler",
            timeout=Duration.seconds(30),
            memory_size=512,  # Increased for faster queries
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant DynamoDB read permissions
        api_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:GetItem",
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/stock-anomalies",
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/stock-anomalies/index/*",
                ],
            )
        )

        # REST API Gateway
        api = apigw.RestApi(
            self, "StockAnomalyApi",
            rest_api_name="Stock Anomaly API",
            description="API for querying stock anomaly data",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                caching_enabled=True,
                cache_ttl=Duration.minutes(5),  # Cache responses for 5 minutes
                cache_cluster_size="0.5",  # 0.5 GB cache
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            ),
        )

        # Lambda integration
        lambda_integration = apigw.LambdaIntegration(
            api_handler,
            proxy=True,
        )

        # Health check endpoint: GET /health
        health = api.root.add_resource("health")
        health.add_method("GET", lambda_integration)

        # Anomalies endpoints: GET /anomalies
        anomalies = api.root.add_resource("anomalies")
        anomalies.add_method("GET", lambda_integration)

        # Ticker-specific endpoint: GET /anomalies/{ticker}
        ticker = anomalies.add_resource("{ticker}")
        ticker.add_method("GET", lambda_integration)
