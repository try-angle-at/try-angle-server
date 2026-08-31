from fastapi import APIRouter, Depends, Request

from src.core.responses import build_success_response
from src.service.auth.jwt_auth import require_user
from src.service.system import system_service
from src.service.system.system_schema import (
    SystemFlushSecRequest,
    SystemFlushSessionRequest,
    SystemSendRequest,
)

# 주의: src/service/logging/logging_api.py(미등록)의 /api/system/log·search는
# 별개의 개발용 시뮬레이터다. 이 라우터가 앱 텔레메트리 수신의 정본이다.
router = APIRouter(prefix="/api/system", tags=["System"])


@router.post("/send")
async def send_batch(request: Request, payload: SystemSendRequest, user=Depends(require_user)):
    """세션 프레임 로그 수신 (1초 = 1배치, 본인/admin 세션만)"""
    ctx = request.app.state.ctx
    result = system_service.save_batch(ctx, payload, user)
    return build_success_response(result)


@router.post("/flushSec")
async def flush_sec(request: Request, payload: SystemFlushSecRequest, user=Depends(require_user)):
    """특정 초 배치 확정 (DB 직행 구조에서는 적재 확인으로 동작, 멱등)"""
    ctx = request.app.state.ctx
    result = system_service.flush_sec(ctx, payload.sId, payload.secSeq, user)
    return build_success_response(result)


@router.post("/flushSession")
async def flush_session(request: Request, payload: SystemFlushSessionRequest, user=Depends(require_user)):
    """세션 전체 확정 (DB 직행 구조에서는 적재 현황 응답, 멱등)"""
    ctx = request.app.state.ctx
    result = system_service.flush_session(ctx, payload.sId, user)
    return build_success_response(result)
