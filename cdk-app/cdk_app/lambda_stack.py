from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_iam as iam,
    aws_sqs as sqs,
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

        # Lambda function for stock scanning
        stock_scanner = _lambda.Function(
            self, "StockScanner",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="stock_scanner.lambda_handler",
            code=_lambda.Code.from_asset("../lambda"),
            function_name="stock-scanner",
            timeout=Duration.seconds(120),
            memory_size=512,  # Increased from 256 for faster execution
            environment={
                "S3_BUCKET": f"stock-scan-data-{self.account}",
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
            retry_attempts=2,
            dead_letter_queue=dlq,
            reserved_concurrent_executions=5,  # Limit concurrency to control costs
        )

        # Grant Lambda permission to read from Parameter Store
        stock_scanner.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:GetParameters"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/stock-tracker/*"
                ],
            )
        )

        # Grant Lambda permission to write to S3
        stock_scanner.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:PutObjectAcl"],
                resources=[
                    f"arn:aws:s3:::stock-scan-data-{self.account}/*"
                ],
            )
        )

        # Grant Lambda permission to write to DynamoDB
        stock_scanner.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:PutItem", "dynamodb:UpdateItem"],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/stock-anomalies"
                ],
            )
        )

        # Grant Lambda permission to publish to SNS
        stock_scanner.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[
                    f"arn:aws:sns:{self.region}:{self.account}:stock-tracker-alerts"
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
