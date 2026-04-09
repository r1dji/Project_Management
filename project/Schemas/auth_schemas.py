from pydantic import BaseModel, Field


class SignUpRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    repeated_password: str = Field(min_length=1)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    message: str
    access_token: str
