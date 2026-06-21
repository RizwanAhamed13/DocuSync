from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: str
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None
    role: Optional[str] = "student"
    college: Optional[str] = None
    department: Optional[str] = None
    year_of_study: Optional[int] = None

class UserLogin(BaseModel):
    username_or_email: str = ""
    username: str = ""
    password: str

class UserPublic(BaseModel):
    id: int
    username: str
    email: str
    display_name: Optional[str] = None
    avatar_initial: Optional[str] = None
    role: str
    college: Optional[str] = None
    department: Optional[str] = None
    year_of_study: Optional[int] = None
    bio: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    created_at: str
    last_login: Optional[str] = None
    dsa_streak: int = 0
    dsa_streak_updated: Optional[str] = None
    dsa_total_solved: int = 0
    leetcode_username: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class AuthResponse(BaseModel):
    user: UserPublic
    access_token: str

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    college: Optional[str] = None
    department: Optional[str] = None
    year_of_study: Optional[int] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
