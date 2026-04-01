import os
import shutil
from http import HTTPStatus
import json

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
    update_document_name,
    delete_document
)
from Services.projects_service import (
    get_proj_by_id,
    get_is_participant,
    update_project_details,
    delete_project,
    create_participation
)

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

    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if proj.owner_id == current_user.user_id or get_is_participant(db, project_id, current_user.user_id):
        old_proj_file_name = f'id_{proj.project_id}_name_{proj.name}'
        docs_folder = os.path.join(os.getcwd(), 'uploaded_files')
        old_proj_upload_files = os.path.join(docs_folder, old_proj_file_name)
        updated_proj = update_project_details(db, proj.project_id, data.name, data.details)
        if updated_proj is not None:
            new_proj_file_name = f'id_{updated_proj.project_id}_name_{updated_proj.name}'
            if os.path.exists(old_proj_upload_files):
                new_file_upload_name = os.path.join(docs_folder, new_proj_file_name)
                os.rename(old_proj_upload_files, new_file_upload_name)
                documents = get_all_documents_for_project(db, updated_proj.project_id)
                for doc in documents:
                    doc_name = ((doc.name.replace("\\", '/')).split('/'))[-1]
                    new_doc_name = os.path.join(new_file_upload_name, doc_name)
                    if update_document_name(db, doc.document_id, new_doc_name):

                        # S3 update file names
                        old_folder_prefix = f'{old_proj_file_name}/{doc_name}'
                        response = s3_client.list_objects_v2(Bucket=AWS_BUCKET_NAME, Prefix=old_folder_prefix)
                        new_folder_prefix = f'{new_proj_file_name}/{doc_name}'
                        if 'Contents' in response:
                            for obj in response['Contents']:
                                old_key = obj['Key']
                                new_key = old_key.replace(old_folder_prefix, new_folder_prefix, 1)

                                # Copy file to new name
                                s3_client.copy_object(
                                    Bucket=AWS_BUCKET_NAME,
                                    CopySource={'Bucket': AWS_BUCKET_NAME, 'Key': old_key},
                                    Key=new_key
                                )
                                # Delete old file
                                s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=old_key)

            return ProjectDetailsResponse(name=updated_proj.name, details=updated_proj.details)
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to update project')

    raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')


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
                os.remove(doc.name)
                s3_file_name_list = ((doc.name.replace("\\", '/')).split('/'))[-2:]
                s3_file_name = '/'.join(s3_file_name_list)
                s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=s3_file_name)

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

    if file.filename.count('+') > 0:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='File name cannot contain +')

    docs_folder = os.path.join(os.getcwd(), 'uploaded_files')
    folder_proj_name = f'id_{project_id}_name_{proj.name}'
    proj_upload_files = os.path.join(docs_folder, folder_proj_name)

    if not os.path.exists(proj_upload_files):
        os.makedirs(proj_upload_files)

    file_path = os.path.join(proj_upload_files, file.filename)
    file_path_s3 = f'{folder_proj_name}/{file.filename}'

    if not get_documents_for_project_by_name(db, project_id, file_path):
        if create_document_for_project(db, project_id, file_path):
            with open(file_path, 'wb') as local_file:
                shutil.copyfileobj(file.file, local_file)
            try:
                s3_client.upload_file(file_path, AWS_BUCKET_NAME, file_path_s3)

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
                        return BaseStrResponse(message='File uploaded successfully')
                    elif lambda_result['status'] == 'error':
                        os.remove(file_path)
                        s3_client.delete_object(Bucket=AWS_BUCKET_NAME, Key=file_path_s3)
                        document = get_documents_for_project_by_name(db, project_id, file_path)
                        delete_document(db, document.document_id)
                        if lambda_result['error'] == 'Exceeded project size limit':
                            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST,
                                                detail='Project size limit exceeded')
                        else:
                            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                                                detail='Failed to upload file')
                    else:
                        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                                            detail='Failed to upload file')
                else:
                    raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                                        detail='Failed to upload file')

            except HTTPException:
                raise
            except Exception as e:
                os.remove(file_path)
                document = get_documents_for_project_by_name(db, project_id, file_path)
                delete_document(db, document.document_id)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f'Upload failed: {str(e)}'
                )
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to create document')

    else:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='File already exists in the project')


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
            name=((doc.name.replace("\\", '/')).split('/'))[-1]
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
