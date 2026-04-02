from sqlalchemy import update

from Database.models import Project, ProjectParticipant


def create_project(db, name, details, current_user):
    new_project = Project(
        name=name,
        details=details,
        owner_id=current_user.user_id
    )

    try:
        db.add(new_project)
        db.commit()
        added_proj = db.query(Project).filter(Project.project_id == new_project.project_id).first()
        new_participation = ProjectParticipant(
            user_id=current_user.user_id,
            project_id=added_proj.project_id
        )
        db.add(new_participation)
        db.commit()
        return new_project
    except Exception as e:
        db.rollback()
        print(e)
        return None


def get_all_participated_projects_for_user_id(db, user_id):
    participated_projects = (
        db.query(Project)
        .join(ProjectParticipant, ProjectParticipant.project_id == Project.project_id)
        .filter(ProjectParticipant.user_id == user_id)
        .all()
    )
    return participated_projects


def get_proj_by_id(db, proj_id):
    return db.query(Project).filter(Project.project_id == proj_id).first()


def get_is_participant(db, proj_id, user_id):
    return db.query(ProjectParticipant).filter_by(user_id=user_id, project_id=proj_id).first() is not None


def update_project_details(db, proj_id, name, details):
    stmt = update(Project).where(Project.project_id == proj_id).values(name=name, details=details)
    try:
        db.execute(stmt)
        db.commit()
        updated_project = db.query(Project).filter(Project.project_id == proj_id).first()
        return updated_project
    except Exception as e:
        db.rollback()
        print(e)
        return False


def delete_project(db, proj_id):
    project = db.query(Project).filter(Project.project_id == proj_id).first()
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


def create_participation(db, proj_id, user_id):
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
