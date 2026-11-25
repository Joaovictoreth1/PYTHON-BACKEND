from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.routers.deps import CurrentUser, get_tag_service
from app.schemas.tag import TagCreate, TagResponse
from app.services.tag_service import TagService

router = APIRouter(prefix="/api/v1/tags", tags=["Tags"])

Service = Annotated[TagService, Depends(get_tag_service)]
TagId = Annotated[int, Path(ge=1)]


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(tag_in: TagCreate, current_user: CurrentUser, service: Service) -> TagResponse:
    return service.create(current_user.id, tag_in)


@router.get("", response_model=list[TagResponse])
def list_tags(
    current_user: CurrentUser,
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[TagResponse]:
    return service.list(current_user.id, skip, limit)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: TagId, current_user: CurrentUser, service: Service) -> Response:
    service.delete(current_user.id, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
