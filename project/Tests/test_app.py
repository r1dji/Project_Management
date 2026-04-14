from fastapi.testclient import TestClient

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from server import app

from Database.db import get_db

from Database.models import Base, Project

client = TestClient(app)

DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session, None, None]:
    database = TestingSessionLocal()
    yield database
    database.close()


app.dependency_overrides[get_db] = override_get_db


def setup_function() -> None:
    Base.metadata.create_all(bind=engine)


def teardown_function() -> None:
    Base.metadata.drop_all(bind=engine)


def test_sign_up() -> None:
    response = client.post(
        "/auth",
        json={
            "username": "test",
            "password": "123",
            "repeated_password": "123"
        }
    )
    assert response.status_code == 201
    assert response.json()["message"] == "User created successfully"


def create_test_user(username: str = "testuser", password: str = "123") -> str:
    client.post(
        "/auth",
        json={
            "username": username,
            "password": password,
            "repeated_password": password
        }
    )

    login_response = client.post(
        "/login",
        json={
            "username": username,
            "password": password
        }
    )
    access_token = login_response.json()["access_token"]
    return access_token


def test_create_project() -> None:
    access_token = create_test_user()
    response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": "Test Project",
            "details": "This is a test project"
        }
    )
    assert response.status_code == 201


def test_update_project_details() -> None:
    access_token = create_test_user()
    response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": "Test Project",
            "details": "This is a test project"
        }
    )
    assert response.status_code == 201
    db = TestingSessionLocal()
    project = db.query(Project).filter(Project.name == "Test Project").first()
    url = f"/project/{project.project_id}/info"
    response = client.put(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": "Test Updated Project",
            "details": "Test Updated Details"
        }
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Test Updated Project"


def test_delete_project() -> None:
    access_token = create_test_user()
    response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": "Test Project",
            "details": "This is a test project"
        }
    )
    assert response.status_code == 201
    db = TestingSessionLocal()
    project = db.query(Project).filter(Project.name == "Test Project").first()
    url = f"/project/{project.project_id}"
    response = client.delete(
        url,
        headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Project deleted successfully"
