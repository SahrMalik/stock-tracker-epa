from aws_cdk import (
    Stack, # Base class for CDK stack
    Duration, # Helper for time values (e.g. Duration.seconds(120) for Lambda timeout)
    aws_lambda as _lambda, 
    aws_events as events, # EventBridge rules (hourly schedule)
    aws_events_targets as targets, # Connects EventBridge to Lambda
    aws_logs as logs, # CloudWatch Log configuration (retention days)
    aws_iam as iam, # IAM roles and policies (least privilege permissions)
    aws_sqs as sqs, # SQS queues 
)
from constructs import Construct

class LambdaStack(Stack):
    """
    CDK Stack for Lambda function and EventBridge scheduling.
    Week 4: Serverless compute and scheduling.
    Week 7: Data collection with anomaly detection.
    Week 8: Error handling with DLQ and retries.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Dead Letter Queue for failed Lambda invocations
        dlq = sqs.Queue(
            self, "StockScannerDLQ",
            queue_name="stock-scanner-dlq",
            retention_period=Duration.days(14),  # Keep failed messages for 14 days
        )

        # Lambda Layer for yfinance dependency
        yfinance_layer = _lambda.LayerVersion(
            self, "YFinanceLayer",
            code=_lambda.Code.from_asset("../lambda-layer"), # Points to the folder containing the yfinance library and its dependencies (numpy, pandas, etc)
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11], # Only works with Python 3.11 Lambdas
            description="yfinance library for stock data",
        )

        # Lambda function for stock scanning
        stock_scanner = _lambda.Function(
            self, "StockScanner",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="stock_scanner.lambda_handler", # File and function
            code=_lambda.Code.from_asset("../lambda"), # Location of app code
            function_name="stock-scanner",
            timeout=Duration.seconds(120), # Max time to run before AWS kills it
            memory_size=512,  # Increased from 256 for faster execution
            environment={
                "S3_BUCKET": f"stock-scan-data-{self.account}",
            }, # environment variables passed to the function
            log_retention=logs.RetentionDays.ONE_WEEK, # Logs auto delete after 7 days 
            retry_attempts=2, # number of tries before sending to DLQ
            dead_letter_queue=dlq,
            reserved_concurrent_executions=5,  # Max 5 instances running at once to save costs
            layers=[yfinance_layer], # attaches yfinance layer
        )

        # Grant Lambda permission to read from Parameter Store
        stock_scanner.add_to_role_policy( # Adds permission to the Lambda's auto generated IAM role
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:GetParameters"], # Read only for parameters under /stock-tracker/ path
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/stock-tracker/*"
                ],
            )
        )

        # Grant Lambda permission to write to S3
        stock_scanner.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:PutObjectAcl"], # Can upload files to S3 & can set access permissions on uploaded files
                resources=[
                    f"arn:aws:s3:::stock-scan-data-{self.account}/*" # Can only write to the specified bucket
                ],
            )
        )

        # Grant Lambda permission to write to DynamoDB
        stock_scanner.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:PutItem", "dynamodb:UpdateItem"], # Can write new anomaly records to the table & can update existing records
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/stock-anomalies" # Can only access the stock-anomalies table
                ],
            )
        )

        # Grant Lambda permission to publish to SNS
        stock_scanner.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"], # Can send messages to an SNS topic
                resources=[
                    f"arn:aws:sns:{self.region}:{self.account}:stock-tracker-alerts" # Can only publish to the stock-tracker-alerts topic
                ],
            )
        )

        # EventBridge rule for hourly execution during market hours
        # Runs every hour from 9:30 AM to 4:00 PM ET, Monday-Friday
        # Cron format: minute hour day-of-month month day-of-week
        # Note: EventBridge uses UTC, so adjust for ET (UTC-5 or UTC-4 for DST)
        schedule_rule = events.Rule(
            self, "StockScannerSchedule",
            schedule=events.Schedule.cron(
                minute="30",  # Run at :30 past the hour
                hour="14-21",  # 9:30 AM - 4:30 PM ET = 14:30 - 21:30 UTC (EST)
                week_day="MON-FRI",
            ),
            description="Trigger stock scanner hourly during market hours",
        )

        # Add Lambda as target for EventBridge rule
        schedule_rule.add_target(targets.LambdaFunction(stock_scanner))
        
        #EventBridge schedule (every hour) → triggers → Scanner Lambda → fetches data → detects anomalies → stores results
