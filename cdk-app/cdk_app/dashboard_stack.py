from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput, # Outputs values after deployment (e.g. prints the CloudFront URL to the terminal)
    aws_s3 as s3, # S3 bucket for hosting the dashboard files
    aws_s3_deployment as s3_deploy, # Auto uploads dashboard/index.html to S3 during deployment
    aws_cloudfront as cloudfront, # CloudFront CDN distribution
    aws_cloudfront_origins as origins, # Connects CloudFront to the S3 bucket as its source
)
from constructs import Construct

class DashboardStack(Stack): # Sixth stack to be deployed. Depends on ApiStack - needs the API endpoint URL to fetch data from 
    """
    CDK Stack for static dashboard hosting.
    Week 9 Day 1: S3 static website with CloudFront.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for static website
        dashboard_bucket = s3.Bucket(
            self, "DashboardBucket",
            bucket_name=f"stock-dashboard-{self.account}", # Unique name using Account ID
            removal_policy=RemovalPolicy.DESTROY, # Deletes bucker when stack is destroyed
            auto_delete_objects=True, # Empties bucket before deletion
        )

        # Deploy dashboard files to S3
        s3_deploy.BucketDeployment(
            self, "DeployDashboard",
            sources=[s3_deploy.Source.asset("../dashboard")], # Takes everything from dashboard/ folder (index.html)
            destination_bucket=dashboard_bucket, # Uploads it to the S3 bucket that was just created
        )

        # CloudFront distribution for HTTPS
        distribution = cloudfront.Distribution(
            self, "DashboardDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(dashboard_bucket), # CloudFront fetches files from S3 bucket. Also auto-creates an Origin Access Identity so only CloudFront can read from the bucket
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS, # If someone visits via HTTP, they're automatically redirected to HTTPS
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED, # Caches dashboard files at edge locations gloablly for fast delivery
            ),
            default_root_object="index.html", # When someone visits CloudFront URL with no path, it serves index.html
        )

        # Output URLs
        CfnOutput(
            self, "CloudFrontURL",
            value=f"https://{distribution.distribution_domain_name}", # Auto generated URL
            description="Dashboard CloudFront URL (HTTPS)"
        )

# Why CloudFront instead of serving directly from S3?
# HTTPS 
# Global CDN (faster worldwide times)
# S3 bucket stays private 
# Caching and compression