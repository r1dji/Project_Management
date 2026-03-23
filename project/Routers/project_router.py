import os
import shutil
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from Database.db import get_db
from Database.models import User
from Routers.auth_router import get_current_user
from Schemas.documents_schemas import DocumentInfo
from Schemas.projects_schemas import ProjectCreate, ProjectDetailsRead
from Services.documents_service import (
    get_documents_for_project_by_name,
    create_document_for_project,
    get_all_documents_for_project
)
from Services.projects_service import (
    get_proj_by_id,
    get_is_participant,
    update_project_details,
    delete_project,
    create_participation
)

router = APIRouter(tags=['Project'])


@router.get('/project/{project_id}/info')
def get_project_details(
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if proj.owner_id == current_user.user_id:
        return JSONResponse(
            content=ProjectDetailsRead(name=proj.name, details=proj.details).model_dump(),
            status_code=HTTPStatus.OK
        )

    if get_is_participant(db, project_id, current_user.user_id):
        return JSONResponse(
            content={
                'project_name': proj.name,
                'details': proj.details
            },
            status_code=HTTPStatus.OK
        )

    raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')


@router.put('/project/{project_id}/info')
def change_project_details(
        project_id: int,
        data: ProjectCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if data.name is None or data.details is None:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Name and details are required')

    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if proj.owner_id == current_user.user_id or get_is_participant(db, project_id, current_user.user_id):
        updated_proj = update_project_details(db, proj.project_id, data.name, data.details)
        if updated_proj is not None:
            return JSONResponse(
                content=ProjectDetailsRead(name=updated_proj.name, details=updated_proj.details).model_dump(),
                status_code=HTTPStatus.OK
            )
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to update project')

    raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')


@router.delete('/project/{project_id}')
def delete_project_and_docs(
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if proj.owner_id == current_user.user_id:
        documents = get_all_documents_for_project(db, project_id)
        if delete_project(db, project_id):
            for doc in documents:
                os.remove(doc.name)
            return JSONResponse(
                content={'message': 'Project deleted successfully'},
                status_code=HTTPStatus.OK
            )
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to delete project')
    else:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Only the owner can delete the project')


@router.post('/project/{project_id}/documents')
def add_documents_to_project(
        project_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    if not get_is_participant(db, project_id, current_user.user_id):
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Not authorized on this project')

    files_not_uploaded = []
    files_uploaded = []

    docs_folder = os.path.join(os.getcwd(), 'uploaded_files')
    proj_upload_files = os.path.join(docs_folder, f'id_{project_id}_name_{proj.name}')

    if not os.path.exists(proj_upload_files):
        os.makedirs(proj_upload_files)

    file_path = os.path.join(proj_upload_files, file.filename)

    if not get_documents_for_project_by_name(db, project_id, file_path):
        if create_document_for_project(db, project_id, file_path):
            with open(file_path, 'wb') as local_file:
                shutil.copyfileobj(file.file, local_file)
            files_uploaded.append(file.filename)
        else:
            files_not_uploaded.append(file.filename)
    else:
        files_not_uploaded.append(file.filename)

    return JSONResponse(
        content={
            'files_uploaded': files_uploaded,
            'files_not_uploaded': files_not_uploaded
        },
        status_code=HTTPStatus.OK
    )


@router.get('/project/{project_id}/documents')
def get_project_documents(
        project_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
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
            name=doc.name
        ).model_dump())

    return JSONResponse(
        content=result,
        status_code=HTTPStatus.OK
    )


@router.post('/project/{project_id}/invite')
def give_access_to_project(
        project_id: int,
        user: str = Query(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    proj = get_proj_by_id(db, project_id)
    if not proj:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Project not found')

    try:
        user = int(user)
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='User id must be a number')

    if proj.owner_id == current_user.user_id:
        if get_is_participant(db, project_id, user):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='User already has access to the project')
        if create_participation(db, project_id, user):
            return JSONResponse(
                content={'message': f'Access to user_id={user} has been granted'},
                status_code=HTTPStatus.OK
            )
        else:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to grant access')
    else:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail='Only the owner can invite users to the project')
