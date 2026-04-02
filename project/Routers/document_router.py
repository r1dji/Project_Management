import os
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from Database.db import get_db
from Database.models import User
from Routers.auth_router import get_current_user
from Schemas.projects_schemas import BaseStrResponse
from Services.documents_service import (
    get_document_by_id,
    delete_document,
    update_document_name,
    get_all_documents_for_project
)
from Services.projects_service import (
    get_is_participant
)
import boto3

from config import settings

from s3_lambda_handle.s3_update_file_handle import s3_update_file_handle

AWS_BUCKET_NAME = settings.AWS_BUCKET_NAME
SQS_QUEUE_URL = settings.AWS_SQS_QUEUE_URL

s3_client = boto3.client('s3', region_name=os.getenv('AWS_REGION'))
sqs_client = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))

router = APIRouter(tags=['Documents'], prefix='/document')


@router.get('/{document_id}')
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
        s3_key = document.name

        response = s3_client.get_object(Bucket=AWS_BUCKET_NAME, Key=s3_key)
        file_content = response['Body'].read()

        display_name = s3_key.split('/')[1]

        return StreamingResponse(
            iter([file_content]),
            media_type='application/octet-stream',
            headers={"Content-Disposition": f"attachment; filename={display_name}"}
        )

    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found in S3')
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                            detail=f'Failed to download document: {str(e)}')


@router.put('/{document_id}')
def update_document(
        document_id: int,
        db: Session = Depends(get_db),
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user)
) -> BaseStrResponse | None:
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')

    if not get_is_participant(db, document.project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='You are not a participant of this project')

    documents = get_all_documents_for_project(db, document.project_id)
    documents_name = [doc.name for doc in documents if document_id != doc.document_id]
    if file.filename in documents_name:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='File already exists in the project')

    if file.filename is not None and '+' in file.filename:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='File name cannot contain +')

    s3_key = f'project_id_{document.project_id}/{file.filename}'

    old_s3_key = document.name
    try:
        file.file.seek(0)
        old_file_content = s3_update_file_handle(AWS_BUCKET_NAME, old_s3_key, s3_key, file.file, SQS_QUEUE_URL)
        if update_document_name(db, document_id, s3_key):
            return BaseStrResponse(message='File updated successfully')
        else:
            s3_update_file_handle(AWS_BUCKET_NAME, s3_key, old_s3_key, old_file_content, SQS_QUEUE_URL)
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to update document')

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f'Failed to update file: {str(e)}')


@router.delete('/{document_id}')
def remove_document(
        document_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> BaseStrResponse:
    document = get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')

    if not get_is_participant(db, document.project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='You are not a participant of this project')

    if delete_document(db, document_id):
        s3_key = document.name
        s3_client.delete_object(Bucket=settings.AWS_BUCKET_NAME, Key=s3_key)

        return BaseStrResponse(message='Document deleted successfully')
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')
