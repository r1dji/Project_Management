import boto3
import os
import json
from PIL import Image
import io
import urllib.parse

s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')

QUEUE_URL = os.getenv('AWS_SQS_QUEUE_URL')
MAX_PROJECT_SIZE = 5 * 1024 * 1024

def lambda_s3_event_handler(event, context):

    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])

    print(f"Event received for: s3://{bucket}/{key}")

    file_extension = key[key.rfind('.'):].lower()

    if file_extension in ['.jpg', '.jpeg', '.png']:
        try:
            tags = s3_client.get_object_tagging(Bucket=bucket, Key=key)
            tag_dict = {tag['Key']: tag['Value'] for tag in tags['TagSet']}

            if not tag_dict.get('processed') == 'true':
                handle_picture_resize(bucket, key)
            else:
                handle_project_size_calc(bucket, key)
        except Exception as e:
            print(f"Error checking tags: {str(e)}")

    else:
        handle_project_size_calc(bucket, key)


def handle_picture_resize(bucket, key):
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_data = response['Body'].read()

        image = Image.open(io.BytesIO(image_data))
        resized_image = image.resize((500, 500), Image.Resampling.LANCZOS)

        resized_bytes = io.BytesIO()

        file_extension = key[key.rfind('.'):].lower()
        if file_extension in ['.jpg', '.jpeg']:
            resized_image.save(resized_bytes, format='JPEG')
        else:
            resized_image.save(resized_bytes, format='PNG')

        resized_bytes.seek(0)

        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=resized_bytes.getvalue(),
            Tagging='processed=true'
        )

        print(f"Image resized to 500x500 and tagged: {key}")

    except Exception as e:
        message = {
            'status': 'error',
            'error': f'Picture resize failed: {str(e)}',
        }

        sqs_client.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        print(f"Error in handle_picture_resize: {str(e)}")


def handle_project_size_calc(bucket, key):
    try:
        folder_name = key.rsplit('/',1)[0]

        folder_size = get_folder_size(bucket, folder_name)

        if folder_size > MAX_PROJECT_SIZE:
            s3_client.delete_object(Bucket=bucket, Key=key)

            message = {
                'status': 'error',
                'error': 'Exceeded project size limit'
            }

            sqs_client.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(message)
            )

        else:
            message = {
                'status': 'success',
                'message': 'File added succesfully'
            }

            sqs_client.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(message)
            )

    except Exception as e:
        message = {
            'status': 'error',
            'error': f'Upload failed: {str(e)}',
        }

        sqs_client.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message)
        )


def get_folder_size(bucket, folder_path):
    total_size = 0

    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=folder_path)

    object_count = 0
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                total_size += obj['Size']
                object_count += 1
                print(f"Object: {obj['Key']}, Size: {obj['Size']} bytes")

    print(f"Folder {folder_path}: Total objects: {object_count}, Total size: {total_size / (1024 * 1024):.2f}MB")
    return total_size
