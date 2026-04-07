from http import HTTPStatus
from typing import List

from fastapi import APIRouter, Depends, HTTPException
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


@router.post('/projects', status_code=HTTPStatus.CREATED)
def add_project(
        data: ProjectCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
) -> ProjectRead:
    if not data.name or not data.details:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Name and details are required')

    if '+' in data.name:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail='Project name cannot contain +')

    project = create_project(db, data.name, data.details, current_user)
    if project:
        return ProjectRead(
            project_id=project.project_id,
            name=project.name,
            details=project.details,
            documents=project.documents
        )
    else:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail='Failed to create project')


@router.get('/projects', status_code=HTTPStatus.OK)
def get_projects(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
) -> List[ProjectRead]:
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

    return result
