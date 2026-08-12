"""Jobs DTO。"""

from pydantic import BaseModel


class JobRunOut(BaseModel):
    id: str
    job_type: str
    business_date: str
    scope_key: str
    status: str
    attempt: int
    max_attempts: int
