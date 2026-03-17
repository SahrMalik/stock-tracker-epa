from aws_cdk import (
    Stack, # Base class
    Duration, # Time helper
    aws_lambda as _lambda, # For the API Lambda function
    aws_apigateway as apigw, #API Gateway resources (REST API, methods, caching, throttling)
    aws_iam as iam, # IAM permissions for the API Lambda
    aws_logs as logs, # CloudWatch log retention
)
from constructs import Construct

class ApiStack(Stack): # Fifth stack to be deployed. Depends on ObservabilityStack (CloudWatch log) & StorageStack (DynamoDB table)
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
            handler="api_handler.lambda_handler", # Entry point file & function
            code=_lambda.Code.from_asset("../lambda"), # Same lambda/ folder as the scanner (both functions live there)
            function_name="stock-api-handler", # Name in AWS console
            timeout=Duration.seconds(30), # Max 30 seconds (shorter than scanner's 120s because API responses should be fast)
            memory_size=512,  # Increased for faster queries
            log_retention=logs.RetentionDays.ONE_WEEK, # CloudWatch autodelete after one week
        )

        # Grant DynamoDB read permissions
        api_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:Query", # Efficient lookup by key (by stock ticker)
                    "dynamodb:Scan", # Full table scan (e.g. all anomalies)
                    "dynamodb:GetItem", # Fetch a single record by exact key
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/stock-anomalies", # Main table
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/stock-anomalies/index/*", # All GSIs (DateIndex, SeverityIndex)
                ],
            )
        )

        # REST API Gateway
        api = apigw.RestApi(
            self, "StockAnomalyApi",
            rest_api_name="Stock Anomaly API", # Name in AWS console
            description="API for querying stock anomaly data",
            deploy_options=apigw.StageOptions(
                stage_name="prod", # The deployment stage
                throttling_rate_limit=100, # Max 100 requests per second
                throttling_burst_limit=200, # Can handle short bursts up to 200 req/s
                caching_enabled=True, # Caches API responses
                cache_ttl=Duration.minutes(5),  # Cache responses for 5 minutes
                cache_cluster_size="0.5",  # 0.5 GB cache, this is what caused the performance improvement
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS, # Allows the CloudFront Dashboard to call the API
                allow_methods=apigw.Cors.ALL_METHODS, # Allows GET, POST, etc. Without CORS, the browser would block the dashboard from calling the API
            ),
        )

        # Lambda integration
        lambda_integration = apigw.LambdaIntegration(
            api_handler,
            proxy=True,
        )

        # Health check endpoint: GET /health
        health = api.root.add_resource("health")
        health.add_method("GET", lambda_integration) # Used by CD pipeline to verify deployment

        # Anomalies endpoints: GET /anomalies
        anomalies = api.root.add_resource("anomalies")
        anomalies.add_method("GET", lambda_integration) # Returns all detected anomalies from DynamoDB. Used by the dashboard (polls every 60 seconds)

        # Ticker-specific endpoint: GET /anomalies/{ticker}
        ticker = anomalies.add_resource("{ticker}")
        ticker.add_method("GET", lambda_integration) # Returns only anomalies for that specific ticker
        
        
        # The request flow:
        # Dashboard → CloudFront → API Gateway (checks cache) → Lambda →
        # DynamoDB → response back
