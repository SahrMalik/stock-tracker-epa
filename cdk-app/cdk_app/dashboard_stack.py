from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct

class DashboardStack(Stack):
    """
    CDK Stack for static dashboard hosting.
    Week 9 Day 1: S3 static website with CloudFront.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for static website
        dashboard_bucket = s3.Bucket(
            self, "DashboardBucket",
            bucket_name=f"stock-dashboard-{self.account}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy dashboard files to S3
        s3_deploy.BucketDeployment(
            self, "DeployDashboard",
            sources=[s3_deploy.Source.asset("../dashboard")],
            destination_bucket=dashboard_bucket,
        )

        # CloudFront distribution for HTTPS
        distribution = cloudfront.Distribution(
            self, "DashboardDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(dashboard_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
        )

        # Output URLs
        CfnOutput(
            self, "CloudFrontURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="Dashboard CloudFront URL (HTTPS)"
        )
