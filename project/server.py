from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from Database.db import create_tables
from Routers.auth_router import router as auth_router
from Routers.document_router import router as documents_router
from Routers.project_router import router as project_router
from Routers.projects_router import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_tables()
    yield


app = FastAPI(title='Project Management', lifespan=lifespan)

app.include_router(auth_router)
app.include_router(project_router)
app.include_router(projects_router)
app.include_router(documents_router)
