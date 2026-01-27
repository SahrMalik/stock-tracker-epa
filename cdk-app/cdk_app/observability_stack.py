from aws_cdk import (
    Stack,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_sns as sns,
    aws_cloudwatch_actions as cw_actions,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class ObservabilityStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudWatch Log Groups
        self.lambda_log_group = logs.LogGroup(
            self,
            "LambdaLogGroup",
            log_group_name="/aws/lambda/stock-scanner",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # SNS Topic for Alerts
        self.alert_topic = sns.Topic(
            self,
            "AlertTopic",
            display_name="Stock Tracker Alerts",
            topic_name="stock-tracker-alerts",
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
                namespace="AWS/Lambda",
                metric_name="Errors",
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Add SNS action to alarm
        pipeline_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
