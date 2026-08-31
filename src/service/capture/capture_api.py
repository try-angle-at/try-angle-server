from fastapi import APIRouter, Depends, Request

from src.core.responses import ResponseStatus, build_response_body, build_success_response
from src.service.auth.jwt_auth import require_admin, require_user
from src.service.capture import capture_service
from src.service.capture.capture_schema import (
    CaptureCreateRequest,
    CaptureDeleteRequest,
    CaptureGetRequest,
    CaptureListRequest,
)

router = APIRouter(prefix="/api/capture", tags=["Capture"])


def _pick_filter(payload: CaptureListRequest):
    z = payload.filter
    if z is not None and not any(v is not None for v in z.model_dump().values()):
        z = None

    def pick(name):
        return getattr(z, name) if z is not None else getattr(payload, name)

    return pick


@router.post("/create")
async def create_capture(request: Request, payload: CaptureCreateRequest, user=Depends(require_user)):
    """일반 촬영 결과 등록 (aesthetic_ref / direct / ai_director)"""
    ctx = request.app.state.ctx
    result = capture_service.create_capture(ctx, payload, user)
    return build_response_body(ResponseStatus.CREATED, result)


@router.post("/list")
async def list_captures(request: Request, payload: CaptureListRequest, user=Depends(require_user)):
    """캡처 목록 조회 (비-admin은 본인 것만)"""
    ctx = request.app.state.ctx
    pick = _pick_filter(payload)
    result = capture_service.list_captures(
        ctx,
        user,
        page=payload.page,
        limit=payload.limit,
        user_id=pick("userId"),
        mode=pick("mode"),
        img_id=pick("imgId"),
        s_id=pick("sId"),
        from_date=pick("fromDate"),
        to_date=pick("toDate"),
        sort_by=payload.sortBy,
        sort_order=payload.sortOrder,
    )
    return build_success_response(result)


@router.post("/get")
async def get_capture(request: Request, payload: CaptureGetRequest, user=Depends(require_user)):
    """캡처 상세 조회 (본인 또는 Admin)"""
    ctx = request.app.state.ctx
    result = capture_service.get_capture(ctx, payload.id, user)
    return build_success_response(result)


@router.post("/delete")
async def delete_capture(request: Request, payload: CaptureDeleteRequest, _=Depends(require_admin)):
    """캡처 삭제 (Admin)"""
    ctx = request.app.state.ctx
    result = capture_service.delete_capture(ctx, payload.id)
    return build_success_response(result)
