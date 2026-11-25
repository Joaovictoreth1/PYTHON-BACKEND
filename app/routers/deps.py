from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models import UserModel
from app.services.comment_service import CommentService
from app.services.project_service import ProjectService
from app.services.stats_service import StatsService
from app.services.tag_service import TagService
from app.services.task_service import TaskService

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[UserModel, Depends(get_current_user)]


def get_project_service(db: DbSession) -> ProjectService:
    return ProjectService(db)


def get_task_service(db: DbSession) -> TaskService:
    return TaskService(db)


def get_stats_service(db: DbSession) -> StatsService:
    return StatsService(db)


def get_tag_service(db: DbSession) -> TagService:
    return TagService(db)


def get_comment_service(db: DbSession) -> CommentService:
    return CommentService(db)
