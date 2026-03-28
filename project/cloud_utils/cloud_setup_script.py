import os
import sys
import boto3
import time
import json
from botocore.config import Config

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_dir)

from config import settings

# Add timeout configuration for large uploads
timeout_config = Config(
    connect_timeout=6000,
    read_timeout=6000,
    retries={'max_attempts': 3}
)

lambda_client = boto3.client('lambda', region_name='eu-north-1', config=timeout_config)
iam_client = boto3.client('iam', region_name='eu-north-1')
s3_client = boto3.client('s3', region_name='eu-north-1')
sqs_client = boto3.client('sqs', region_name='eu-north-1')

functions = [
    {
        'name': 'lambda_s3_event_handler',
        'zip_file': 'lambda_s3_event_handler.zip',
        'handler': 'lambda_s3_event_handler.lambda_s3_event_handler',
        'trigger': True
    }
]


def create_s3_bucket(bucket_name):
    """Create S3 bucket if it doesn't exist"""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"S3 bucket '{bucket_name}' already exists")
        return True

    except Exception as e:
        if e.response['Error']['Code'] == '404':
            print(f"S3 bucket '{bucket_name}' not found. Creating...")

            try:
                s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={
                        'LocationConstraint': 'eu-north-1'
                    }
                )
                print(f"S3 bucket '{bucket_name}' created successfully")
                return True

            except Exception as e:
                print(f"Error creating bucket: {str(e)}")
                return False
        else:
            print(f"Error checking bucket: {str(e)}")
            return False


def create_iam_role(role_name, bucket_name):
    """Create IAM role for Lambda if it doesn't exist"""
    try:
        role = iam_client.get_role(RoleName=role_name)
        print(f"Role '{role_name}' already exists")
        return role['Role']['Arn']

    except iam_client.exceptions.NoSuchEntityException:
        print(f"Role '{role_name}' not found. Creating...")

        try:
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "lambda.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }

            role_response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='Role for Lambda S3 trigger with read/write access'
            )

            print(f"Role created: {role_response['Role']['Arn']}")
            print("Attaching policies...")

            iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
            )

            s3_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:GetObjectVersion",
                            "s3:PutObject",
                            "s3:DeleteObject",
                            "s3:GetObjectTagging",
                            "s3:PutObjectTagging"
                        ],
                        "Resource": f"arn:aws:s3:::{bucket_name}/*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:ListBucket"
                        ],
                        "Resource": f"arn:aws:s3:::{bucket_name}"
                    }
                ]
            }

            iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName='LambdaS3ReadWritePolicy',
                PolicyDocument=json.dumps(s3_policy)
            )

            print("Policies attached successfully")
            time.sleep(10)

            return role_response['Role']['Arn']

        except Exception as e:
            print(f"Error creating role: {str(e)}")
            return None


def check_and_create_lambda(role_arn, function_config, queue_url):
    """Create Lambda function if it doesn't exist"""
    function_name = function_config['name']
    zip_file = function_config['zip_file']
    handler = function_config['handler']

    # Use script directory, not current working directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(script_dir, zip_file)

    print(f"ZIP file path: {zip_path}")
    print(f"ZIP file exists: {os.path.exists(zip_path)}")
    if os.path.exists(zip_path):
        zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
        print(f"ZIP file size: {zip_size_mb:.2f}MB")

    try:
        response = lambda_client.get_function(FunctionName=function_name)
        print(f"Function '{function_name}' already exists")
        print("Waiting for Lambda function to be fully initialized...")
        time.sleep(5)
        return response['Configuration']['FunctionArn']

    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"Function '{function_name}' not found. Creating...")

        try:
            with open(zip_path, 'rb') as f:
                zip_content = f.read()

            response = lambda_client.create_function(
                FunctionName=function_name,
                Runtime='python3.14',
                Role=role_arn,
                Handler=handler,
                Timeout=600,
                Code={
                    'ZipFile': zip_content
                },
                Environment={
                    'Variables': {
                        'AWS_SQS_QUEUE_URL': queue_url
                    }
                }
            )
            print(f"Function created successfully: {response['FunctionArn']}")
            print("Waiting for Lambda function to be fully initialized...")
            time.sleep(5)
            return response['FunctionArn']

        except FileNotFoundError:
            print(f"ERROR: ZIP file not found at {zip_path}")
            return None
        except Exception as e:
            print(f"Error creating function: {str(e)}")
            return None

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return None


def add_s3_trigger(lambda_arn, bucket_name, function_name):
    """Add S3 bucket event trigger to Lambda function"""
    try:
        print(f"Adding S3 invoke permission to Lambda '{function_name}'...")
        try:
            lambda_client.add_permission(
                FunctionName=function_name,
                StatementId=f'AllowS3Invoke-{function_name}',
                Action='lambda:InvokeFunction',
                Principal='s3.amazonaws.com',
                SourceArn=f'arn:aws:s3:::{bucket_name}'
            )
            print("Permission added successfully")
        except lambda_client.exceptions.ResourceConflictException:
            print("Permission already exists")

        print(f"Configuring S3 bucket '{bucket_name}' to trigger Lambda...")

        # Get existing notification configuration
        try:
            existing_config = s3_client.get_bucket_notification_configuration(Bucket=bucket_name)
        except Exception as e:
            print(f"{str(e)}")
            existing_config = {}

        # Extract existing Lambda configs
        existing_lambdas = existing_config.get('LambdaFunctionConfigurations', [])

        # Check if this function is already configured
        already_configured = any(conf['LambdaFunctionArn'] == lambda_arn for conf in existing_lambdas)

        if already_configured:
            print(f"S3 trigger already configured for {function_name}")
            return True

        # Add new Lambda config (no file extension filter)
        lambda_config = {
            'LambdaFunctionArn': lambda_arn,
            'Events': ['s3:ObjectCreated:*']
        }

        existing_lambdas.append(lambda_config)

        notification_config = {
            'LambdaFunctionConfigurations': existing_lambdas
        }

        s3_client.put_bucket_notification_configuration(
            Bucket=bucket_name,
            NotificationConfiguration=notification_config
        )
        print(f"S3 trigger configured successfully for {function_name}!")
        return True

    except Exception as e:
        print(f"Error adding S3 trigger: {str(e)}")
        return False


def create_sqs_queue(queue_name):
    """Create SQS queue for Lambda-API communication"""
    try:
        # Check if queue exists
        response = sqs_client.get_queue_url(QueueName=queue_name)
        queue_url = response['QueueUrl']
        print(f"SQS queue '{queue_name}' already exists")
        return queue_url

    except sqs_client.exceptions.QueueDoesNotExist:
        print(f"SQS queue '{queue_name}' not found. Creating...")

        try:
            response = sqs_client.create_queue(
                QueueName=queue_name,
                Attributes={
                    'VisibilityTimeout': '300',  # 5 minutes
                    'MessageRetentionPeriod': '345600',  # 4 days
                    'ReceiveMessageWaitTimeSeconds': '20'  # Long polling
                }
            )
            queue_url = response['QueueUrl']
            print(f"SQS queue '{queue_name}' created successfully")
            return queue_url

        except Exception as e:
            print(f"Error creating SQS queue: {str(e)}")
            return None


def attach_sqs_policy_to_lambda_role(queue_url, role_name):
    """Attach policy to Lambda role to allow sending messages to SQS"""
    try:
        from urllib.parse import urlparse
        parsed_url = urlparse(queue_url)

        # Extract account ID and queue name from path
        path_parts = parsed_url.path.strip('/').split('/')
        account_id = path_parts[0]
        queue_name = path_parts[1]

        # Extract region from netloc (e.g., sqs.eu-north-1.amazonaws.com)
        region = parsed_url.netloc.split('.')[1]

        # Construct proper ARN
        queue_arn = f'arn:aws:sqs:{region}:{account_id}:{queue_name}'

        print(f"Queue ARN: {queue_arn}")

        sqs_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "sqs:SendMessage"
                    ],
                    "Resource": queue_arn
                }
            ]
        }

        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName='LambdaSQSSendPolicy',
            PolicyDocument=json.dumps(sqs_policy)
        )

        print(f"SQS policy attached to role '{role_name}'")
        return True

    except Exception as e:
        print(f"Error attaching SQS policy: {str(e)}")
        return None


if __name__ == "__main__":
    print("Starting Lambda deployment automation...\n")

    bucket_name = settings.AWS_BUCKET_NAME
    queue_name = settings.AWS_SQS_QUEUE_NAME
    role_name = settings.ROLE_NAME

    bucket_created = create_s3_bucket(bucket_name)

    if not bucket_created:
        print("Failed to create/access S3 bucket. Exiting.")
        exit(1)

    role_arn = create_iam_role(role_name, bucket_name)

    if not role_arn:
        print("Failed to create/get IAM role. Exiting.")
        exit(1)

    all_success = True
    lambda_arns = {}

    queue_url = create_sqs_queue(queue_name)
    if not queue_url:
        print("Failed to create/access SQS queue. Exiting.")
        exit(1)

    if not attach_sqs_policy_to_lambda_role(queue_url, role_name):
        print("Failed to attach SQS policy. Exiting.")
        exit(1)

    for func_config in functions:
        print(f"\n--- Creating {func_config['name']} ---")
        lambda_arn = check_and_create_lambda(role_arn, func_config, queue_url)

        if lambda_arn:
            lambda_arns[func_config['name']] = lambda_arn

            if func_config.get('trigger', True):
                trigger_success = add_s3_trigger(
                    lambda_arn,
                    bucket_name,
                    func_config['name']
                )
                if not trigger_success:
                    all_success = False
        else:
            all_success = False

    if all_success:
        print("\n✓ Deployment completed successfully!")
    else:
        print("\n✗ Deployment had errors!")
        exit(1)