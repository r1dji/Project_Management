from pydantic import BaseModel


class SignUpRequest(BaseModel):
    username: str
    password: str
    repeated_password: str


class LoginRequest(BaseModel):
    username: str
    password: str
