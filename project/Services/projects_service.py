from typing import List, Optional

from sqlalchemy import update, select
from sqlalchemy.orm import Session

from Database.models import Project, ProjectParticipant, User


def create_project(db: Session, name: str, details: str, current_user: User) -> Optional[Project]:
    new_project = Project(
        name=name,
        details=details,
        owner_id=current_user.user_id
    )

    try:
        db.add(new_project)
        db.commit()
        new_participation = ProjectParticipant(
            user_id=current_user.user_id,
            project_id=new_project.project_id
        )
        db.add(new_participation)
        db.commit()
        return new_project
    except Exception as e:
        db.rollback()
        print(e)
        return None


def get_all_participated_projects_for_user_id(db: Session, user_id: int) -> List[Project]:
    stmt = (
        select(Project)
        .join(ProjectParticipant, ProjectParticipant.project_id == Project.project_id)
        .where(ProjectParticipant.user_id == user_id)
    )
    return list(db.scalars(stmt))


def get_proj_by_id(db: Session, proj_id: int) -> Optional[Project]:
    return db.scalars(select(Project).where(Project.project_id == proj_id)).first()


def get_is_participant(db: Session, proj_id: int, user_id: int) -> bool:
    return db.scalars(select(ProjectParticipant).where(
        (ProjectParticipant.user_id == user_id) & (ProjectParticipant.project_id == proj_id))).first() is not None


def update_project_details(db: Session, proj_id: int, name: str, details: str) -> Optional[Project]:
    stmt = update(Project).where(Project.project_id == proj_id).values(name=name, details=details)
    try:
        db.execute(stmt)
        db.commit()
        updated_project = db.scalars(select(Project).where(Project.project_id == proj_id)).first()
        return updated_project
    except Exception as e:
        db.rollback()
        print(e)
        return None


def delete_project(db: Session, proj_id: int) -> bool:
    project = db.scalars(select(Project).where(Project.project_id == proj_id)).first()
    if not project:
        return False
    try:
        db.delete(project)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(e)
        return False


def create_participation(db: Session, proj_id: int, user_id: int) -> bool:
    new_participation = ProjectParticipant(
        user_id=user_id,
        project_id=proj_id
    )
    try:
        db.add(new_participation)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(e)
        return False
