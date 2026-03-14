from sqlalchemy import update

from models import Documents


def get_documents_for_project_by_name(db, proj_id, doc_name):
    return db.query(Documents).filter_by(project_id=proj_id, name=doc_name).first()


def create_document_for_project(db, proj_id, doc_name):
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


def get_all_documents_for_project(db, proj_id):
    return db.query(Documents).filter_by(project_id=proj_id).all()


def get_document_by_id(db, doc_id):
    return db.query(Documents).filter_by(document_id=doc_id).first()


def delete_document(db, doc_id):
    document = db.query(Documents).filter_by(document_id=doc_id).first()
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


def update_document_name(db, document_id, file_path):
    stmt = update(Documents).where(Documents.document_id == document_id).values(name=file_path)
    try:
        db.execute(stmt)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(e)
        return False
