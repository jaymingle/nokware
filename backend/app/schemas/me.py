from pydantic import BaseModel

from app.services.auth import Role


class MeResponse(BaseModel):
    user_id: str
    name: str
    email: str
    role: Role
    department: str | None  # department team ID, for the department role only
    department_name: str | None
