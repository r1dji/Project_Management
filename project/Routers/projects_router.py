from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from Database.db import get_db
from Database.models import User
from Routers.auth_router import get_current_user
from Schemas.projects_schemas import ProjectCreate, ProjectRead
from Services.documents_service import (
    get_all_documents_for_project,
)
from Services.projects_service import (
    create_project,
    get_all_participated_projects_for_user_id,
)

router = APIRouter(tags=['Projects'])


@router.post('/projects')
def add_project(
        data: ProjectCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if not data.name or not data.details:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Name and details are required')

    if create_project(db, data.name, data.details, current_user):
        return JSONResponse(
            content={'message': 'Project created successfully'},
            status_code=201
        )
    else:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to create project')


@router.get('/projects')
def get_projects(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    result = []
    participated_projects = get_all_participated_projects_for_user_id(db, current_user.user_id)
    for proj in participated_projects:
        documents = get_all_documents_for_project(db, proj.project_id)
        documents = [(((doc.name).replace("\\", '/')).split('/'))[-1] for doc in documents]
        result.append(ProjectRead(
            project_id=proj.project_id,
            name=proj.name,
            details=proj.details,
            documents=documents
        ))

    return JSONResponse(
        content=[item.model_dump() for item in result],
        status_code=HTTPStatus.OK
    )
