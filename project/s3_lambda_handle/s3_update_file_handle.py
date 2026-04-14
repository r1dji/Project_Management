import boto3
from typing import BinaryIO

from s3_lambda_handle.s3_file_upload_handle import s3_file_upload_handle


def s3_update_file_handle(bucket: str, old_s3_key: str, new_s3_key: str,
                          file_content: BinaryIO | bytes, sqs_queue_url: str) -> bytes:
    s3_client = boto3.client('s3')
    old_file_response = s3_client.get_object(Bucket=bucket, Key=old_s3_key)
    old_file_content = old_file_response['Body'].read()
    if new_s3_key != old_s3_key:
        s3_client.delete_object(Bucket=bucket, Key=old_s3_key)
        try:
            s3_file_upload_handle(bucket, new_s3_key, file_content, sqs_queue_url)
            return old_file_content
        except Exception as e:
            s3_file_upload_handle(bucket, old_s3_key, old_file_content, sqs_queue_url)
            raise e
    else:
        s3_file_upload_handle(bucket, new_s3_key, file_content, sqs_queue_url)
        return old_file_content
