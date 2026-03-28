import os
import shutil
from http import HTTPStatus
import json

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session

from Database.db import get_db
from Database.models import User
from Routers.auth_router import get_current_user
from Services.documents_service import (
    get_document_by_id,
    delete_document,
    update_document_name,
    get_all_documents_for_project
)
from Services.projects_service import (
    get_proj_by_id,
    get_is_participant
)
import boto3


from config import settings

AWS_BUCKET_NAME = settings.AWS_BUCKET_NAME
SQS_QUEUE_URL = settings.AWS_SQS_QUEUE_URL

s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')

router = APIRouter(tags=['Documents'])


@router.get('/document/{document_id}')
def download_document(
        document_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')

    if not get_is_participant(db, document.project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='You are not a participant of this project')

    try:
        s3_file_name_list = ((document.name.replace("\\", '/')).split('/'))[-2:]
        folder = s3_file_name_list[0]
        filename = s3_file_name_list[1]

        s3_key = f'{folder}/{filename}'

        response = s3_client.get_object(Bucket=AWS_BUCKET_NAME, Key=s3_key)
        file_content = response['Body'].read()

        display_name = os.path.basename(document.name.replace("\\", "/"))

        with open(document.name, 'wb') as local_file:
            local_file.write(file_content)

        return FileResponse(
            document.name,
            filename=display_name,
        )

    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found in S3')
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                            detail=f'Failed to download document: {str(e)}')


@router.put('/document/{document_id}')
def update_document(
        document_id: int,
        db: Session = Depends(get_db),
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user)
):
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')

    if not get_is_participant(db, document.project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='You are not a participant of this project')

    proj = get_proj_by_id(db, document.project_id)

    documents = get_all_documents_for_project(db, document.project_id)
    documents_name = [doc.name for doc in documents]
    if file.filename in documents_name:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='File already exists in the project')

    docs_folder = os.path.join(os.getcwd(), 'uploaded_files')
    proj_files_path = f'id_{document.project_id}_name_{proj.name}'
    proj_upload_files = os.path.join(docs_folder, proj_files_path)

    file_path = os.path.join(proj_upload_files, file.filename)
    s3_file_name_list = ((document.name.replace("\\", '/')).split('/'))[-2:]
    s3_file_name = '/'.join(s3_file_name_list)

    s3_new_file_name = f'id_{document.project_id}_name_{proj.name}/{file.filename}'

    s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_file_name)

    if file_path != document.name:
        with open(file_path, 'wb') as local_file:
            shutil.copyfileobj(file.file, local_file)

        try:
            s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_file_name)
            s3_client.upload_file(file_path, AWS_BUCKET_NAME, s3_new_file_name)

            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20
            )

            if 'Messages' in response:
                message = response['Messages'][0]
                lambda_result = json.loads(message['Body'])

                sqs_client.delete_message(
                    QueueUrl=SQS_QUEUE_URL,
                    ReceiptHandle=message['ReceiptHandle']
                )

                if lambda_result['status'] == 'success':
                    os.remove(document.name)
                    if update_document_name(db, document_id, file_path):
                        return JSONResponse(
                            content={'message': 'File updated successfully'},
                            status_code=HTTPStatus.OK
                        )
                    else:
                        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Document not updated')
                elif lambda_result['status'] == 'error':
                    os.remove(file_path)
                    s3_client.upload_file(document.name, AWS_BUCKET_NAME, s3_file_name)
                    if lambda_result['error'] == 'Exceeded project size limit':
                        return JSONResponse(
                            content={'message': 'Project size limit exceeded'},
                            status_code=HTTPStatus.CONTENT_TOO_LARGE
                        )
                    else:
                        return JSONResponse(
                            content={'message': 'Failed to update file'},
                            status_code=HTTPStatus.INTERNAL_SERVER_ERROR
                        )
            else:
                os.remove(file_path)
                s3_client.upload_file(document.name, AWS_BUCKET_NAME, s3_file_name)
                raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to upload file')

        except HTTPException:
            raise
        except Exception as e:
            os.remove(file_path)
            s3_client.upload_file(document.name, AWS_BUCKET_NAME, s3_file_name)
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f'Upload failed: {str(e)}'
            )

    else:
        fn_splited = file.filename.rsplit('.', 1)
        file_path = os.path.join(proj_upload_files, proj_files_path, fn_splited[0] + '_new.' + fn_splited[1])
        with open(file_path, 'wb') as local_file:
            shutil.copyfileobj(file.file, local_file)

        try:
            s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_file_name)
            s3_client.upload_file(file_path, AWS_BUCKET_NAME, s3_new_file_name)

            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20
            )

            if 'Messages' in response:
                message = response['Messages'][0]
                lambda_result = json.loads(message['Body'])

                sqs_client.delete_message(
                    QueueUrl=SQS_QUEUE_URL,
                    ReceiptHandle=message['ReceiptHandle']
                )

                if lambda_result['status'] == 'success':
                    os.remove(document.name)
                    os.rename(file_path, document.name)

                    return JSONResponse(
                        content={'message': 'File updated successfully'},
                        status_code=HTTPStatus.OK
                    )

                elif lambda_result['status'] == 'error':
                    os.remove(file_path)
                    s3_client.upload_file(document.name, AWS_BUCKET_NAME, s3_file_name)
                    if lambda_result['error'] == 'Exceeded project size limit':
                        return JSONResponse(
                            content={'message': 'Project size limit exceeded'},
                            status_code=HTTPStatus.CONTENT_TOO_LARGE
                        )
                    else:
                        return JSONResponse(
                            content={'message': 'Failed to update file'},
                            status_code=HTTPStatus.INTERNAL_SERVER_ERROR
                        )
            else:
                os.remove(file_path)
                s3_client.upload_file(document.name, AWS_BUCKET_NAME, s3_file_name)
                raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to upload file')

        except HTTPException:
            raise
        except Exception as e:
            os.remove(file_path)
            s3_client.upload_file(document.name, AWS_BUCKET_NAME, s3_file_name)
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f'Upload failed: {str(e)}'
            )


@router.delete('/document/{document_id}')
def remove_document(
        document_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')

    if not get_is_participant(db, document.project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='You are not a participant of this project')

    if delete_document(db, document_id):
        os.remove(document.name)

        s3_file_name_list = ((document.name.replace("\\", '/')).split('/'))[-2:]
        s3_client.delete_object(Bucket=settings.AWS_BUCKET_NAME, Key='/'.join(s3_file_name_list))

        return JSONResponse(status_code=HTTPStatus.OK, content={'message': 'Document deleted successfully'})
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')
