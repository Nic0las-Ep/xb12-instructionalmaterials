#!/usr/bin/env python3
"""CDK entry point for the XB12 instructional-materials registry."""
import os

import aws_cdk as cdk

from xb12_stack.xb12_stack import Xb12Stack

app = cdk.App()

# The application reuses resources that already exist in the target account,
# so the stack must be deployed to that specific account/region.
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT", "391959657971"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-west-2"),
)

Xb12Stack(
    app,
    "Xb12InstructionalMaterialsStack",
    env=env,
    description="XB12 textbook & learning-platform registry (Lambdas, API, CloudFront UI)",
)

app.synth()
