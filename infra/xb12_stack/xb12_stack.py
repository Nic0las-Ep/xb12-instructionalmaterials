"""
XB12 Instructional-Materials Registry - CDK stack.

Reuses the existing DynamoDB tables and OpenSearch Serverless collection in the
account and adds the compute + delivery layer:

  * A Lambda layer with shared code (xb12_common).
  * Four Lambda functions (isbn lookup, search, create resource, course adoptions).
  * A REST API Gateway (CORS enabled) fronting the functions.
  * A private S3 bucket + CloudFront distribution (OAC) serving the frontend,
    with a generated config.json carrying the API base URL.
"""

import json
import os

from aws_cdk import (
    Aws,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_opensearchserverless as aoss
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

# ---- Existing resources in the account (reused, not created) --------------
RESOURCE_TABLE = "Resource-index"
HISTORY_TABLE = "Textbookhistory-index"
COLLECTION_NAME = "resource-index"
COLLECTION_ID = "78ef54x7of34cghphp6g"
AOSS_ENDPOINT = f"https://{COLLECTION_ID}.us-west-2.aoss.amazonaws.com"
# Vector-enabled index (knn_vector mapping) for semantic similarity search.
AOSS_INDEX = "resources_v2"
LOW_COST_THRESHOLD = "50"
# Amazon Bedrock Titan Text Embeddings v2 (1024-dim, normalized).
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIM = "1024"
# Minimum cosine similarity for a semantic search hit to be shown (tunable).
SIMILARITY_MIN_SCORE = "0.37"
# New table (created by this stack) that stores finalized class submissions.
SUBMISSIONS_TABLE = "Xb12-submissions"

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "..", "backend"))
_FRONTEND = os.path.abspath(os.path.join(_HERE, "..", "..", "frontend"))


class Xb12Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        collection_arn = (
            f"arn:aws:aoss:{self.region}:{self.account}:collection/{COLLECTION_ID}"
        )
        resource_table_arn = (
            f"arn:aws:dynamodb:{self.region}:{self.account}:table/{RESOURCE_TABLE}"
        )
        history_table_arn = (
            f"arn:aws:dynamodb:{self.region}:{self.account}:table/{HISTORY_TABLE}"
        )

        # ---- Shared Lambda execution role --------------------------------
        lambda_role = iam.Role(
            self,
            "Xb12LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:BatchGetItem",
                    "dynamodb:BatchWriteItem",
                ],
                resources=[
                    resource_table_arn,
                    f"{resource_table_arn}/index/*",
                    history_table_arn,
                    f"{history_table_arn}/index/*",
                ],
            )
        )
        # Data-plane access to the OpenSearch Serverless collection.
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["aoss:APIAccessAll"],
                resources=[collection_arn],
            )
        )
        # Amazon Bedrock access for Titan text embeddings (semantic search).
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1",
                ],
            )
        )

        # ---- AOSS data access policy for the Lambda role -----------------
        # Grants the execution role read/write on the collection's indexes.
        access_policy_doc = [
            {
                "Rules": [
                    {
                        "ResourceType": "index",
                        "Resource": [f"index/{COLLECTION_NAME}/*"],
                        "Permission": [
                            "aoss:CreateIndex",
                            "aoss:DeleteIndex",
                            "aoss:UpdateIndex",
                            "aoss:DescribeIndex",
                            "aoss:ReadDocument",
                            "aoss:WriteDocument",
                        ],
                    },
                    {
                        "ResourceType": "collection",
                        "Resource": [f"collection/{COLLECTION_NAME}"],
                        "Permission": [
                            "aoss:CreateCollectionItems",
                            "aoss:UpdateCollectionItems",
                            "aoss:DescribeCollectionItems",
                        ],
                    },
                ],
                "Principal": [lambda_role.role_arn],
                "Description": "XB12 Lambda access to resource-index",
            }
        ]
        aoss.CfnAccessPolicy(
            self,
            "Xb12LambdaAossAccess",
            name="xb12-lambda-access",
            type="data",
            policy=json.dumps(access_policy_doc),
        )

        # ---- Submissions table (new; stores finalized class submissions) --
        submissions_table = dynamodb.Table(
            self,
            "Xb12SubmissionsTable",
            table_name=SUBMISSIONS_TABLE,
            partition_key=dynamodb.Attribute(
                name="id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,  # keep submissions if stack is torn down
        )
        submissions_table.grant_read_write_data(lambda_role)

        # ---- Shared code layer -------------------------------------------
        common_layer = _lambda.LayerVersion(
            self,
            "Xb12CommonLayer",
            code=_lambda.Code.from_asset(os.path.join(_BACKEND, "layer")),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Shared xb12_common helpers (xb12 classifier, AOSS, registries)",
        )

        common_env = {
            "RESOURCE_TABLE": RESOURCE_TABLE,
            "HISTORY_TABLE": HISTORY_TABLE,
            "SUBMISSIONS_TABLE": SUBMISSIONS_TABLE,
            "AOSS_ENDPOINT": AOSS_ENDPOINT,
            "AOSS_INDEX": AOSS_INDEX,
            "LOW_COST_THRESHOLD": LOW_COST_THRESHOLD,
            "EMBED_MODEL_ID": EMBED_MODEL_ID,
            "EMBED_DIM": EMBED_DIM,
            "SIMILARITY_MIN_SCORE": SIMILARITY_MIN_SCORE,
            # Optional paid price source (ISBNdb). Leave blank to disable; when
            # set, ISBN lookups return the list price (MSRP) automatically.
            "ISBNDB_API_KEY": os.environ.get("ISBNDB_API_KEY", ""),
        }

        functions_code = _lambda.Code.from_asset(os.path.join(_BACKEND, "functions"))

        def make_fn(id_, handler_file, timeout=30):
            return _lambda.Function(
                self,
                id_,
                runtime=_lambda.Runtime.PYTHON_3_12,
                handler=f"{handler_file}.handler",
                code=functions_code,
                role=lambda_role,
                layers=[common_layer],
                environment=common_env,
                timeout=Duration.seconds(timeout),
                memory_size=256,
            )

        isbn_fn = make_fn("IsbnLookupFn", "isbn_lookup")
        search_fn = make_fn("SearchResourcesFn", "search_resources")
        create_fn = make_fn("CreateResourceFn", "create_resource")
        course_fn = make_fn("CourseResourcesFn", "course_resources")
        submit_fn = make_fn("SubmitClassFn", "submit_class", timeout=60)
        submissions_fn = make_fn("SubmissionsFn", "submissions")

        # ---- REST API ----------------------------------------------------
        api = apigw.RestApi(
            self,
            "Xb12Api",
            rest_api_name="xb12-instructional-materials",
            description="API for the XB12 textbook & learning-platform registry",
            deploy_options=apigw.StageOptions(stage_name="prod"),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # /isbn-lookup  (POST)
        isbn_res = api.root.add_resource("isbn-lookup")
        isbn_res.add_method("POST", apigw.LambdaIntegration(isbn_fn))

        # /resources (POST)  and  /resources/search (GET)
        resources_res = api.root.add_resource("resources")
        resources_res.add_method("POST", apigw.LambdaIntegration(create_fn))
        search_res = resources_res.add_resource("search")
        search_res.add_method("GET", apigw.LambdaIntegration(search_fn))

        # /course-resources (GET, POST)
        course_res = api.root.add_resource("course-resources")
        course_res.add_method("GET", apigw.LambdaIntegration(course_fn))
        course_res.add_method("POST", apigw.LambdaIntegration(course_fn))

        # /submit-class (POST) - finalize a class submission
        submit_res = api.root.add_resource("submit-class")
        submit_res.add_method("POST", apigw.LambdaIntegration(submit_fn))

        # /submissions (GET)  and  /submissions/{id} (GET, PUT, DELETE)
        submissions_res = api.root.add_resource("submissions")
        submissions_res.add_method("GET", apigw.LambdaIntegration(submissions_fn))
        submission_item = submissions_res.add_resource("{id}")
        submission_item.add_method("GET", apigw.LambdaIntegration(submissions_fn))
        submission_item.add_method("PUT", apigw.LambdaIntegration(submissions_fn))
        submission_item.add_method("DELETE", apigw.LambdaIntegration(submissions_fn))

        # ---- Frontend hosting: S3 (private) + CloudFront (OAC) -----------
        site_bucket = s3.Bucket(
            self,
            "Xb12SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        distribution = cloudfront.Distribution(
            self,
            "Xb12Distribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
            comment="XB12 instructional-materials registry UI",
        )

        # Deploy the static frontend plus a generated runtime config.json that
        # tells the frontend where the API lives.
        s3deploy.BucketDeployment(
            self,
            "Xb12SiteDeployment",
            sources=[
                s3deploy.Source.asset(_FRONTEND),
                s3deploy.Source.json_data("config.json", {"apiBaseUrl": api.url}),
            ],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # ---- Outputs -----------------------------------------------------
        CfnOutput(self, "ApiUrl", value=api.url, description="API Gateway base URL")
        CfnOutput(
            self,
            "SiteUrl",
            value=f"https://{distribution.distribution_domain_name}",
            description="CloudFront URL for the registry UI",
        )
        CfnOutput(self, "SiteBucketName", value=site_bucket.bucket_name)
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)
