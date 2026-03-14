from fastapi import FastAPI

from db import create_tables

from contextlib import asynccontextmanager

from auth import router as auth_router
from Routers.projects_router import router as projects_router
from Routers.documents_router import router as documents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(title='Project Management', lifespan=lifespan)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(documents_router)
