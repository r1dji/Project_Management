import boto3

from http import HTTPStatus
from typing import BinaryIO

from fastapi import HTTPException

import json


def s3_file_upload_handle(bucket: str, key: str, file_content: BinaryIO | bytes, sqs_queue_url: str) -> None:
    s3_client = boto3.client('s3')
    sqs_client = boto3.client('sqs')

    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=file_content
    )

    response = sqs_client.receive_message(
        QueueUrl=sqs_queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20
    )

    if 'Messages' not in response:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to upload file')

    message = response['Messages'][0]
    lambda_result = json.loads(message['Body'])

    sqs_client.delete_message(
        QueueUrl=sqs_queue_url,
        ReceiptHandle=message['ReceiptHandle']
    )

    if lambda_result['status'] == 'success':
        return
    else:
        if lambda_result['error'] == 'Exceeded project size limit':
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Project size limit exceeded')
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to upload file')
