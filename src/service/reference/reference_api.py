from fastapi import APIRouter, Depends, Request

from src.core.responses import build_success_response

from src.service.auth.jwt_auth import require_admin, require_user
from src.service.reference import reference_service
from src.service.reference.reference_schema import (
    RefCreateRequest,
    RefDeleteRequest,
    RefGetRequest,
    RefListRequest,
    RefUpdateRequest,
)

router = APIRouter(prefix="/api/ref", tags=["Reference"])


@router.post("/list")
async def list_refs(request: Request, payload: RefListRequest, _=Depends(require_user)):
    ctx = request.app.state.ctx
    result = reference_service.list_refs(
        ctx,
        page=payload.page,
        limit=payload.limit,
        ctg_id=payload.filter.ctgId if payload.filter else None,
        title=payload.filter.title if payload.filter else None,
        kwd=payload.filter.kwd if payload.filter else None,
        kwd_groups=payload.filter.kwdGroups if payload.filter else None,
    )
    return build_success_response(result)


@router.post("/get")
async def get_ref(request: Request, payload: RefGetRequest, _=Depends(require_user)):
    ctx = request.app.state.ctx
    result = reference_service.get_ref(ctx, payload.id)
    return build_success_response(result)


@router.post("/create")
async def create_ref(request: Request, payload: RefCreateRequest, user=Depends(require_admin)):
    ctx = request.app.state.ctx
    result = reference_service.create_ref(ctx, payload, user_id=user["id"])
    return build_success_response(result)


@router.post("/update")
async def update_ref(request: Request, payload: RefUpdateRequest, _=Depends(require_admin)):
    ctx = request.app.state.ctx
    result = reference_service.update_ref(ctx, payload)
    return build_success_response(result)


@router.post("/delete")
async def delete_ref(request: Request, payload: RefDeleteRequest, _=Depends(require_admin)):
    ctx = request.app.state.ctx
    result = reference_service.delete_ref(ctx, payload.id)
    return build_success_response(result)
