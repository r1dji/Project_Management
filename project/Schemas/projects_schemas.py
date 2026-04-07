from typing import List

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    details: str


class ProjectDetailsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    details: str


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    name: str
    details: str
    documents: List[str]


class BaseStrResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
