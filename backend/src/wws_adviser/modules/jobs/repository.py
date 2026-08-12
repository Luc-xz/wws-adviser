"""Jobs 仓储。"""

from sqlalchemy.orm import Session as DBSession

from wws_adviser.modules.jobs.models import JobRun


def get_by_id(db: DBSession, job_id: str) -> JobRun | None:
    return db.get(JobRun, job_id)
