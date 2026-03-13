#!/usr/bin/env python3
import os

import aws_cdk as cdk

from cdk_app.cdk_app_stack import CdkAppStack
from cdk_app.observability_stack import ObservabilityStack
from cdk_app.lambda_stack import LambdaStack
from cdk_app.storage_stack import StorageStack
from cdk_app.secrets_stack import SecretsStack
from cdk_app.api_stack import ApiStack
from cdk_app.dashboard_stack import DashboardStack


app = cdk.App()

# Define environment
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT', '529088281783'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
)

# Deploy observability stack
ObservabilityStack(app, "ObservabilityStack", env=env)

# Deploy storage stack 
StorageStack(app, "StorageStack", env=env)

# Deploy secrets stack 
SecretsStack(app, "SecretsStack", env=env)

# Deploy Lambda stack 
LambdaStack(app, "LambdaStack", env=env)

# Deploy API stack 
ApiStack(app, "ApiStack", env=env)

# Deploy dashboard stack 
DashboardStack(app, "DashboardStack", env=env)

# Original stack
CdkAppStack(app, "CdkAppStack", env=env)

app.synth()
