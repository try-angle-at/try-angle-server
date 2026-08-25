from fastapi import APIRouter, Depends, Request

from src.service.auth.jwt_auth import require_admin, require_user
from src.service.ctg import ctg_service
from src.service.ctg.ctg_schema import (
    CtgCreateRequest,
    CtgDeleteRequest,
    CtgGetRequest,
    CtgListRequest,
    CtgUpdateRequest,
)
from src.core.responses import build_success_response

router = APIRouter(prefix="/api/ctg", tags=["Category"])


@router.post("/list")
async def list_ctgs(request: Request, payload: CtgListRequest, _=Depends(require_user)):
    ctx = request.app.state.ctx
    result = ctg_service.list_ctgs(ctx, page=payload.page, limit=payload.limit)
    return build_success_response(result)


@router.post("/get")
async def get_ctg(request: Request, payload: CtgGetRequest, _=Depends(require_user)):
    ctx = request.app.state.ctx
    result = ctg_service.get_ctg(ctx, payload.id)
    return build_success_response(result)


@router.post("/create")
async def create_ctg(request: Request, payload: CtgCreateRequest, _=Depends(require_admin)):
    ctx = request.app.state.ctx
    result = ctg_service.create_ctg(ctx, payload)
    return build_success_response(result)


@router.post("/update")
async def update_ctg(request: Request, payload: CtgUpdateRequest, _=Depends(require_admin)):
    ctx = request.app.state.ctx
    result = ctg_service.update_ctg(ctx, payload)
    return build_success_response(result)


@router.post("/delete")
async def delete_ctg(request: Request, payload: CtgDeleteRequest, _=Depends(require_admin)):
    ctx = request.app.state.ctx
    result = ctg_service.delete_ctg(ctx, payload.id)
    return build_success_response(result)
