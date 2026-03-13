from aws_cdk import (
    Stack, # Base class for the CDK stack
    RemovalPolicy, # Controls what happens to resources when you delete the stack (keep or destroy the data)
    Duration, # Time helper (used for S3 lifecycle policy)
    aws_dynamodb as dynamodb, # DynamoDB table and index resources
    aws_s3 as s3, # S3 bucket resources
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
            table_name="stock-anomalies", # The actual table name in AWS
            partition_key=dynamodb.Attribute(
                name="ticker", # Primary key part 1. Groups anomalies by stock symbol
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", # Primary key part 2. Orders anomalies by time within each ticker. Together with partition key, every record is uniquely identified
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # On-demand pricing, pay per read/write
            point_in_time_recovery=True,  # Enable backups
            removal_policy=RemovalPolicy.DESTROY,  # If the CDK stack gets deleted, the table gets deleted too  
        )

        # Global Secondary Index for querying by date
        self.anomalies_table.add_global_secondary_index(
            index_name="DateIndex", # Name of index
            partition_key=dynamodb.Attribute( 
                name="date", # Query by date instead of ticker
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", # Ordered by time within each date
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,  # Include all attributes
        )

        # GSI for querying by severity
        self.anomalies_table.add_global_secondary_index(
            index_name="SeverityIndex",
            partition_key=dynamodb.Attribute(
                name="severity", # Query by severity
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", # Ordered by time 
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # S3 bucket for raw scan data
        self.scan_data_bucket = s3.Bucket(
            self, "ScanDataBucket",
            bucket_name=f"stock-scan-data-{self.account}", # Unique bucket name using AWS account ID
            versioned=True,  # Enable versioning
            encryption=s3.BucketEncryption.S3_MANAGED,  # SSE-S3 encryption, AWS manages keys automatically. Every file stored is encrypted
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldScans",
                    enabled=True,
                    expiration=Duration.days(30),  # Delete after 30 days
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,  # Deletes bucket when stack is destroyed - for dev/testing
            auto_delete_objects=True,  # Empties the bucket before deleting it
        )
