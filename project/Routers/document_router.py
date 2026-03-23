import os
import shutil
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session

from Database.db import get_db
from Database.models import User
from Routers.auth_router import get_current_user
from Services.documents_service import (
    get_document_by_id,
    delete_document,
    update_document_name
)
from Services.projects_service import (
    get_proj_by_id,
    get_is_participant
)

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

    if os.path.isfile(document.name):
        display_name = os.path.basename(document.name.replace("\\", "/"))
        return FileResponse(document.name, filename=display_name)
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document doesnt exist')


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

    docs_folder = os.path.join(os.getcwd(), 'uploaded_files')
    proj_upload_files = os.path.join(docs_folder, f'id_{document.project_id}_name_{proj.name}')

    file_path = os.path.join(proj_upload_files, file.filename)

    if document.name != file_path:
        os.remove(document.name)

    if update_document_name(db, document_id, file_path):
        with open(file_path, 'wb') as local_file:
            shutil.copyfileobj(file.file, local_file)
        return JSONResponse(status_code=HTTPStatus.OK, content={'message': 'Document updated successfully'})
    else:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Document not updated')


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
        return JSONResponse(status_code=HTTPStatus.OK, content={'message': 'Document deleted successfully'})
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail='Document not found')
