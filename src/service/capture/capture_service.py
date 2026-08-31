import json
import time

from fastapi import HTTPException

from src.app_context import AppContext
from src.service.auth.auth_schema import UserRole
from src.service.capture.capture_schema import (
    CaptureCreateRequest,
    CaptureItem,
    CaptureListResponse,
)
from src.utils.db_utils import execute_query
from src.utils.payload_utils import sanitize_json

_VALID_SORT_BY = {"capturedAt", "cDate", "id"}
_VALID_SORT_ORDER = {"asc", "desc"}

_SELECT_ITEM = """
    SELECT
        c.id, c.userId, u.nickname AS userName, c.sId, c.imgId,
        c.mode, c.captureUrl, c.analysis, c.capturedAt, c.cDate, c.uDate
    FROM tb_capture c
    LEFT JOIN tb_user u ON u.id = c.userId
"""


def _is_admin_role(role) -> bool:
    return role in (UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value)


def _parse_json_field(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _row_to_item(row: tuple) -> CaptureItem:
    return CaptureItem(
        id=row[0],
        userId=row[1],
        userName=row[2],
        sId=row[3],
        imgId=row[4],
        mode=row[5],
        captureUrl=row[6],
        analysis=_parse_json_field(row[7]),
        capturedAt=row[8],
        cDate=row[9],
        uDate=row[10],
    )


def _get_capture_row(ctx: AppContext, capture_id: int) -> CaptureItem:
    rows = execute_query(ctx.db_handler, f"{_SELECT_ITEM} WHERE c.id = %s", (capture_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Capture not found")
    return _row_to_item(rows[0])


def _ensure_session_linkable(ctx: AppContext, session_id: str, user: dict) -> None:
    """sId 연결은 본인(또는 admin) 세션만 — system/send의 소유권 규칙과 대칭."""
    rows = execute_query(ctx.db_handler, "SELECT userId FROM tb_session WHERE id = %s", (session_id,))
    if not rows:
        raise HTTPException(status_code=400, detail="Session not found")
    if _is_admin_role(user.get("role")):
        return
    if rows[0][0] != user.get("id"):
        raise HTTPException(status_code=403, detail="Session access denied")


def create_capture(ctx: AppContext, payload: CaptureCreateRequest, user: dict) -> CaptureItem:
    """일반 촬영 결과 등록"""
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    if payload.sId:
        _ensure_session_linkable(ctx, payload.sId, user)
    if payload.imgId is not None:
        rows = execute_query(ctx.db_handler, "SELECT id FROM tb_img WHERE id = %s", (payload.imgId,))
        if not rows:
            raise HTTPException(status_code=400, detail="Reference image not found")

    # analysis는 무검증 통과지만 NaN/Infinity는 MySQL JSON이 거부하므로 소독 (system/send와 동일 정책)
    analysis_json = None
    if payload.analysis is not None:
        analysis_json = json.dumps(sanitize_json(payload.analysis), ensure_ascii=False)

    now = int(time.time())
    sql = """
        INSERT INTO tb_capture (userId, sId, imgId, mode, captureUrl, analysis, capturedAt, cDate, uDate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        user["id"],
        payload.sId,
        payload.imgId,
        payload.mode.strip(),
        payload.captureUrl,
        analysis_json,
        payload.capturedAt,
        now,
        now,
    )

    conn = ctx.db_handler.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            new_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        if ctx.log:
            ctx.log.error(f"Failed to create capture: {e}")
        raise HTTPException(status_code=500, detail="Failed to create capture")

    return _get_capture_row(ctx, new_id)


def list_captures(
    ctx: AppContext,
    user: dict,
    page: int = 1,
    limit: int = 20,
    user_id: int | None = None,
    mode: str | None = None,
    img_id: int | None = None,
    s_id: str | None = None,
    from_date: int | None = None,
    to_date: int | None = None,
    sort_by: str = "capturedAt",
    sort_order: str = "desc",
) -> CaptureListResponse:
    """캡처 목록 조회. 비-admin은 본인 것만 (session/list와 동일 스코핑 규칙)."""
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    sort_by = (sort_by or "capturedAt").strip()
    sort_order = (sort_order or "desc").strip().lower()
    if sort_by not in _VALID_SORT_BY:
        raise HTTPException(status_code=400, detail="Invalid sortBy value")
    if sort_order not in _VALID_SORT_ORDER:
        raise HTTPException(status_code=400, detail="Invalid sortOrder value")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=400, detail="fromDate must be less than or equal to toDate")

    if not _is_admin_role(user.get("role")):
        user_id = user.get("id")

    filters = []
    params: list = []
    for clause, value in (
        ("c.userId = %s", user_id),
        ("c.mode = %s", mode),
        ("c.imgId = %s", img_id),
        ("c.sId = %s", s_id),
        ("c.capturedAt >= %s", from_date),
        ("c.capturedAt <= %s", to_date),
    ):
        if value is not None:
            filters.append(clause)
            params.append(value)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    count_rows = execute_query(ctx.db_handler, f"SELECT COUNT(*) FROM tb_capture c {where_clause}", tuple(params))
    total = count_rows[0][0] if count_rows else 0

    offset = (page - 1) * limit
    rows = execute_query(
        ctx.db_handler,
        f"{_SELECT_ITEM} {where_clause} ORDER BY c.{sort_by} {sort_order.upper()} LIMIT %s OFFSET %s",
        tuple(params + [limit, offset]),
    )
    items = [_row_to_item(row) for row in rows]
    return CaptureListResponse(items=items, total=total, page=page, limit=limit)


def get_capture(ctx: AppContext, capture_id: int, user: dict) -> CaptureItem:
    """캡처 상세 — 본인 또는 admin만 (snap과 달리 공개 피드가 아닌 사적 촬영물)."""
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    item = _get_capture_row(ctx, capture_id)
    if not _is_admin_role(user.get("role")) and item.userId != user.get("id"):
        raise HTTPException(status_code=403, detail="Capture access denied")
    return item


def delete_capture(ctx: AppContext, capture_id: int) -> dict:
    """캡처 삭제 (Admin — 계약 §3-2)"""
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    _get_capture_row(ctx, capture_id)
    conn = ctx.db_handler.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM tb_capture WHERE id = %s", (capture_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        if ctx.log:
            ctx.log.error(f"Failed to delete capture: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete capture")
    return {"id": capture_id}
