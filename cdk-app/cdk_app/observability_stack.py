from aws_cdk import (
    Stack,
    aws_logs as logs, # CloudWatch log groups
    aws_cloudwatch as cloudwatch, # CloudWatch metrics and alarms 
    aws_sns as sns, # SNS topics for sending alert notifications
    aws_sns_subscriptions as sns_subs, # Subscribes endpoints to SNS topics
    aws_lambda as _lambda, # For the notification Lambda
    aws_cloudwatch_actions as cw_actions, # Connects CloudWatch alarsm to SNS (alarm triggers -> send notification)
    aws_iam as iam, # IAM permissions for the Notifications Lambda
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class ObservabilityStack(Stack): # First stack to be deployed
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudWatch Log Groups
        self.lambda_log_group = logs.LogGroup(
            self,
            "LambdaLogGroup", # CDK logical ID - used internally by CloudFormation to track this resource
            log_group_name="/aws/lambda/stock-scanner", # AWS Lambda automatically sends logs to a log group with this naming pattern
            retention=logs.RetentionDays.ONE_WEEK, # Logs auto-delete after 7 days
            removal_policy=RemovalPolicy.DESTROY, # Deletes log group when stack is destroyed
        )

        # SNS Topic for Alerts
        self.alert_topic = sns.Topic(
            self,
            "AlertTopic",
            display_name="Stock Tracker Alerts",
            topic_name="stock-tracker-alerts", # Resource name in AWS
        )

        # Lambda function for Slack notifications
        notification_handler = _lambda.Function(
            self, "NotificationHandler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="notification_handler.lambda_handler", # file and function
            code=_lambda.Code.from_asset("../lambda"),
            function_name="stock-notification-handler", # Name in AWS console
            timeout=Duration.seconds(30), # Quick job, just sends a HTTP request to Slack
            memory_size=128, # Smallest allocation. Only needs to format a message and send it, no heavy processing
            log_retention=logs.RetentionDays.ONE_WEEK, # 7 day log retention
        )
        
        # Grant permission to read Slack webhook from Parameter Store
        notification_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"], # Can read from parameter store
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/stock-tracker/slack-webhook" # Can only read the Slack webhook URL
                ],
            )
        )

        # Subscribe Lambda to SNS topic
        self.alert_topic.add_subscription(
            sns_subs.LambdaSubscription(notification_handler)
        )

        # CloudWatch Dashboard
        self.dashboard = cloudwatch.Dashboard(
            self,
            "StockTrackerDashboard",
            dashboard_name="stock-tracker-dashboard",
        )

        # Add initial widgets
        self.dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# Stock Tracker Monitoring\n\nInitial dashboard - metrics will be added as components are deployed.",
                width=24,
                height=2,
            )
        )

        # CloudWatch Alarm for Pipeline Failures (placeholder)
        pipeline_alarm = cloudwatch.Alarm(
            self,
            "PipelineFailureAlarm",
            alarm_name="stock-tracker-pipeline-failures",
            alarm_description="Alert when CI/CD pipeline fails",
            metric=cloudwatch.Metric(
                namespace="AWS/Lambda", # Monitors Lambda service metrics
                metric_name="Errors", # Tracks error count
                statistic="Sum", # Total errors in the period
                period=Duration.minutes(5), # Checks every 5 minutes
            ),
            threshold=1, # Triggers if one or more errors occur
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING, # If no data, assume everything is fine
        )

        # Add SNS action to alarm
        pipeline_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic)) # When alarm triggers -> publish to SNS topic -> Notification Lambda -> Slack alert
