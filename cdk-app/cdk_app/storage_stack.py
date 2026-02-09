from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)
from constructs import Construct

class StorageStack(Stack):
    """
    CDK Stack for data storage infrastructure.
    Week 5: DynamoDB and S3 setup.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB table for anomaly findings
        self.anomalies_table = dynamodb.Table(
            self, "AnomaliesTable",
            table_name="stock-anomalies",
            partition_key=dynamodb.Attribute(
                name="ticker",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # On-demand pricing
            point_in_time_recovery=True,  # Enable backups
            removal_policy=RemovalPolicy.DESTROY,  # For dev/testing
        )

        # Global Secondary Index for querying by date
        self.anomalies_table.add_global_secondary_index(
            index_name="DateIndex",
            partition_key=dynamodb.Attribute(
                name="date",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,  # Include all attributes
        )

        # GSI for querying by severity
        self.anomalies_table.add_global_secondary_index(
            index_name="SeverityIndex",
            partition_key=dynamodb.Attribute(
                name="severity",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # S3 bucket for raw scan data
        self.scan_data_bucket = s3.Bucket(
            self, "ScanDataBucket",
            bucket_name=f"stock-scan-data-{self.account}",
            versioned=True,  # Enable versioning
            encryption=s3.BucketEncryption.S3_MANAGED,  # SSE-S3 encryption
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldScans",
                    enabled=True,
                    expiration=Duration.days(30),  # Delete after 30 days
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,  # For dev/testing
            auto_delete_objects=True,  # Clean up on stack deletion
        )
