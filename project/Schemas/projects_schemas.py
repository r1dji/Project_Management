from typing import List

from pydantic import BaseModel, ConfigDict, Field

from Schemas.documents_schemas import DocumentInfo


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
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
    documents: List[DocumentInfo]
