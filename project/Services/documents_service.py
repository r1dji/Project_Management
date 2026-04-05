from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from Database.models import Documents


def get_documents_for_project_by_name(db: Session, proj_id: int, doc_name: str) -> Optional[Documents]:
    return db.scalars(select(Documents).where((Documents.project_id == proj_id) & (Documents.name == doc_name))).first()


def create_document_for_project(db: Session, proj_id: int, doc_name: str) -> bool:
    new_doc = Documents(
        name=doc_name,
        project_id=proj_id
    )
    try:
        db.add(new_doc)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(e)
        return False


def get_all_documents_for_project(db: Session, proj_id: int) -> List[Documents]:
    documents = db.scalars(select(Documents).where(Documents.project_id == proj_id))
    return list(documents)


def get_document_by_id(db: Session, doc_id: int) -> Optional[Documents]:
    return db.scalars(select(Documents).where(Documents.document_id == doc_id)).first()


def delete_document(db: Session, doc_id: int) -> bool:
    document = db.scalars(select(Documents).where(Documents.document_id == doc_id)).first()
    if not document:
        return False
    try:
        db.delete(document)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(e)
        return False


def update_document_name(db: Session, document_id: int, file_path: str) -> bool:
    stmt = update(Documents).where(Documents.document_id == document_id).values(name=file_path)
    try:
        db.execute(stmt)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(e)
        return False
