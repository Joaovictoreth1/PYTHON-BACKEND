from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.security import get_current_user
from app.db.session import get_db
from app.models import UserModel
from app.schemas.auth import (
    LogoutRequest,
    RefreshRequest,
    TokenPairResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.auth_service import AuthService
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticação"])


def get_auth_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> AuthService:
    return AuthService(db, request.app.state.settings)


Service = Annotated[AuthService, Depends(get_auth_service)]
CurrentUser = Annotated[UserModel, Depends(get_current_user)]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, service: Service) -> UserResponse:
    return service.register(payload)


@router.post("/login", response_model=TokenPairResponse)
def login(payload: UserLogin, service: Service) -> TokenPairResponse:
    return service.login(payload)


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(payload: RefreshRequest, service: Service) -> TokenPairResponse:
    return service.refresh(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, current_user: CurrentUser, service: Service) -> Response:
    service.logout(payload.refresh_token, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
