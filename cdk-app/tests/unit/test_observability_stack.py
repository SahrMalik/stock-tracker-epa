import aws_cdk as core
import aws_cdk.assertions as assertions
from cdk_app.observability_stack import ObservabilityStack


def test_log_group_created():
    """Test that CloudWatch Log Group is created with correct retention."""
    app = core.App()
    stack = ObservabilityStack(app, "TestObservabilityStack")
    template = assertions.Template.from_stack(stack)

    # Assert Log Group exists
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": "/aws/lambda/stock-scanner",
            "RetentionInDays": 7,
        },
    )


def test_sns_topic_created():
    """Test that SNS topic for alerts is created."""
    app = core.App()
    stack = ObservabilityStack(app, "TestObservabilityStack")
    template = assertions.Template.from_stack(stack)

    # Assert SNS Topic exists
    template.has_resource_properties(
        "AWS::SNS::Topic",
        {
            "DisplayName": "Stock Tracker Alerts",
            "TopicName": "stock-tracker-alerts",
        },
    )


def test_dashboard_created():
    """Test that CloudWatch Dashboard is created."""
    app = core.App()
    stack = ObservabilityStack(app, "TestObservabilityStack")
    template = assertions.Template.from_stack(stack)

    # Assert Dashboard exists
    template.has_resource_properties(
        "AWS::CloudWatch::Dashboard",
        {
            "DashboardName": "stock-tracker-dashboard",
        },
    )


def test_alarm_created():
    """Test that CloudWatch Alarm is created with SNS action."""
    app = core.App()
    stack = ObservabilityStack(app, "TestObservabilityStack")
    template = assertions.Template.from_stack(stack)

    # Assert Alarm exists
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": "stock-tracker-pipeline-failures",
            "Threshold": 1,
            "EvaluationPeriods": 1,
        },
    )
