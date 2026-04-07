import os
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from Database.db import get_db
from Database.models import User
from Routers.auth_router import get_current_user
from Schemas.documents_schemas import DocumentInfo
from Schemas.projects_schemas import ProjectCreate, ProjectDetailsResponse, BaseStrResponse
from Services.documents_service import (
    get_documents_for_project_by_name,
    create_document_for_project,
    get_all_documents_for_project,
)
from Services.projects_service import (
    get_proj_by_id,
    get_is_participant,
    update_project_details,
    delete_project,
    create_participation
)

from s3_lambda_handle.s3_file_upload_handle import s3_file_upload_handle

from typing import List

from config import settings

import boto3

s3_client = boto3.client('s3', region_name=os.getenv('AWS_REGION'))
sqs_client = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))

AWS_BUCKET_NAME = settings.AWS_BUCKET_NAME
SQS_QUEUE_URL = settings.AWS_SQS_QUEUE_URL
router = APIRouter(tags=['Project'], prefix='/project')


@router.get('/{project_id}/info', status_code=HTTPStatus.OK)
def get_project_details(
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
) -> ProjectDetailsResponse:
    proj = get_proj_by_id(db, project_id)

    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if proj.owner_id == current_user.user_id:
        return ProjectDetailsResponse(name=proj.name, details=proj.details)

    if get_is_participant(db, project_id, current_user.user_id):
        return ProjectDetailsResponse(name=proj.name, details=proj.details)

    raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')


@router.put('/{project_id}/info', status_code=HTTPStatus.OK)
def change_project_details(
        project_id: int,
        data: ProjectCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> ProjectDetailsResponse:
    if data.name is None or data.details is None:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Name and details are required')

    if '+' in data.name:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Project name cannot contain +')

    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if not get_is_participant(db, project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')

    updated_proj = update_project_details(db, project_id, data.name, data.details)

    if updated_proj is not None:
        return ProjectDetailsResponse(name=updated_proj.name, details=updated_proj.details)
    else:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to update project')


@router.delete('/{project_id}', status_code=HTTPStatus.OK)
def delete_project_and_docs(
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> BaseStrResponse:
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if proj.owner_id == current_user.user_id:
        documents = get_all_documents_for_project(db, project_id)
        if delete_project(db, project_id):
            for doc in documents:
                s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=doc.name)
            return BaseStrResponse(message='Project deleted successfully')
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to delete project')
    else:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Only the owner can delete the project')


@router.post('/{project_id}/documents', status_code=HTTPStatus.CREATED)
def add_documents_to_project(
        project_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> BaseStrResponse:
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if not get_is_participant(db, project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')

    if file.filename is not None and '+' in file.filename:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='File name cannot contain +')

    s3_key = f'project_id_{project_id}/{file.filename}'

    if get_documents_for_project_by_name(db, project_id, s3_key):
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='File already exists in the project')

    try:
        file.file.seek(0)
        s3_file_upload_handle(AWS_BUCKET_NAME, s3_key, file.file, SQS_QUEUE_URL)
        if create_document_for_project(db, project_id, s3_key):
            return BaseStrResponse(message='File uploaded successfully')
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to create document')

    except HTTPException:
        raise
    except Exception as e:
        s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_key)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f'Failed to upload file: {str(e)}')


@router.get('/{project_id}/documents', status_code=HTTPStatus.OK)
def get_project_documents(
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> List[DocumentInfo]:
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if not get_is_participant(db, project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')

    result = []
    documents = get_all_documents_for_project(db, project_id)
    for doc in documents:
        result.append(DocumentInfo(
            id=doc.document_id,
            name=doc.name.split('/')[1]
        ))

    return result


@router.post('/{project_id}/invite', status_code=HTTPStatus.OK)
def give_access_to_project(
        project_id: int,
        user: str = Query(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> BaseStrResponse:
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    try:
        user = int(user)
    except ValueError:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='User id must be a number')

    if proj.owner_id == current_user.user_id:
        if get_is_participant(db, project_id, user):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='User already has access to the project')
        if create_participation(db, project_id, user):
            return BaseStrResponse(message='Access granted successfully')
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to grant access')
    else:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Only the owner can invite users to the project')
