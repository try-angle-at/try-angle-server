import json
import time

import pymysql
from fastapi import APIRouter, Depends, HTTPException, Request

from src.app_context import AppContext
from src.core.id_generator import generate_sid
from src.core.responses import ResponseStatus, build_response_body, build_success_response
from src.service.auth.auth_schema import UserRole
from src.service.auth.jwt_auth import require_user
from src.service.session.session_schema import (
    SessionDetailRequest,
    SessionDetailResponse,
    SessionEndRequest,
    SessionItem,
    SessionListRequest,
    SessionListResponse,
    SessionRecord,
    SessionStartRequest,
    SessionStatus,
)
from src.utils.db_utils import execute_query


router = APIRouter(prefix="/api/session", tags=["Session"])

# 집계 서브쿼리: admin SysList가 소비하는 텔레메트리 요약 (22224a6 복원)
_AGG_COLS = """,
            (SELECT MAX(rt.stuckSec) FROM tb_rt_snapshot rt WHERE rt.sId = s.id) AS maxStuckSec,
            (SELECT COUNT(*) FROM tb_rt_snapshot rt WHERE rt.sId = s.id) AS snapshotCount,
            (SELECT rt.feedback FROM tb_rt_snapshot rt WHERE rt.sId = s.id AND rt.feedback IS NOT NULL ORDER BY rt.secSeq DESC LIMIT 1) AS mainFeedback"""

_Q = {
    "SR": f"""
            SELECT
                s.id,
                s.userId,
                u.nickname AS userName,
                s.imgId,
                s.sDate,
                s.eDate,
                s.device,
                s.sStat,
                s.cDate,
                s.uDate{_AGG_COLS}
            FROM tb_session s
            LEFT JOIN tb_user u ON u.id = s.userId
            WHERE s.id = %s
        """,
    "LB": f"""
        SELECT
            s.id, s.userId, u.nickname AS userName, s.imgId,
            s.sDate, s.eDate, s.device, s.sStat, s.cDate, s.uDate{_AGG_COLS}
        FROM tb_session s
        LEFT JOIN tb_user u ON s.userId = u.id
        WHERE 1=1
    """,
    "LC": """
        SELECT COUNT(DISTINCT s.id)
        FROM tb_session s
        LEFT JOIN tb_user u ON s.userId = u.id
        WHERE 1=1
    """,
    "SI": """
        INSERT INTO tb_session (id, userId, imgId, sDate, eDate, device, sStat, cDate, uDate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
    "SU": """
        UPDATE tb_session
        SET eDate = %s,
            sStat = %s,
            uDate = %s
        WHERE id = %s
    """,
    "SNAP": """
        SELECT secSeq, rawPayload
        FROM tb_rt_snapshot
        WHERE {where}
        ORDER BY secSeq ASC
        LIMIT %s
    """,
}


_W = {
    "user": "AND s.userId = %s",
    "img": "AND s.imgId = %s",
    "stat": "AND s.sStat = %s",
    "sdate": "AND s.sDate >= %s",
    "edate": "AND s.sDate <= %s",
}


def _parse_json_field(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def _row_to_session_item(row: tuple) -> SessionItem:
    return SessionItem(
        id=row[0],
        userId=row[1],
        userName=row[2],
        imgId=row[3],
        sDate=row[4],
        eDate=row[5],
        device=_parse_json_field(row[6]),
        sStat=row[7],
        cDate=row[8],
        uDate=row[9],
        maxStuckSec=row[10] if len(row) > 10 else None,
        snapshotCount=row[11] if len(row) > 11 else None,
        mainFeedback=row[12] if len(row) > 12 else None,
    )


def _get_session_row(ctx: AppContext, session_id: str) -> SessionItem:
    rows = execute_query(ctx.db_handler, _Q["SR"], (session_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Session not found")
    return _row_to_session_item(rows[0])


def _is_admin_role(user_role: str | UserRole | None) -> bool:
    return user_role in (UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value)


def _get_owned_session_row(
    ctx: AppContext,
    session_id: str,
    user_id: int,
    user_role: str | UserRole | None = None,
) -> SessionItem:
    session = _get_session_row(ctx, session_id)
    if _is_admin_role(user_role):
        return session
    if session.userId != user_id:
        raise HTTPException(status_code=403, detail="Session access denied")
    return session


def _extract_records(raw_payload) -> list[dict]:
    """tb_rt_snapshot.rawPayload({"records": [...]})에서 프레임 목록 추출 (22224a6 복원)"""
    payload = _parse_json_field(raw_payload)
    if not isinstance(payload, dict):
        return []
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _list_sessions_impl(
    ctx: AppContext,
    page: int = 1,
    limit: int = 20,
    user_id: int = None,
    img_id: int = None,
    s_stat: int = None,
    sDate: int = None,
    eDate: int = None,
    category: str = None,
    feedback: str = None,
    stuck_sec: float = None,
    can_capture: str = None,
) -> SessionListResponse:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    offset = (page - 1) * limit
    where_clauses: list[str] = []
    base_params: list = []

    for k, v in (("user", user_id), ("img", img_id), ("stat", s_stat), ("sdate", sDate), ("edate", eDate)):
        if v is None:
            continue
        where_clauses.append(_W[k])
        base_params.append(v)

    # 텔레메트리 스냅샷 필터 (22224a6 복원): 조건이 있을 때만 EXISTS 서브쿼리 부착.
    # stuckSec >= 0은 항상 참이므로 0 초과일 때만 필터로 취급한다.
    snapshot_filters_active = (
        any(v is not None for v in (category, feedback, can_capture))
        or (stuck_sec is not None and stuck_sec > 0)
    )
    if snapshot_filters_active:
        sub_clauses = ["rt.sId = s.id"]
        if category is not None:
            sub_clauses.append("rt.category = %s")
            base_params.append(category)
        if feedback is not None:
            sub_clauses.append("rt.feedback LIKE %s")
            base_params.append(f"%{feedback}%")
        if stuck_sec is not None and stuck_sec > 0:
            sub_clauses.append("rt.stuckSec >= %s")
            base_params.append(stuck_sec)
        if can_capture is not None:
            sub_clauses.append("rt.canCapture = %s")
            base_params.append(can_capture)
        where_clauses.append(f"AND EXISTS (SELECT 1 FROM tb_rt_snapshot rt WHERE {' AND '.join(sub_clauses)})")

    where_str = " ".join(where_clauses)
    count_res = execute_query(ctx.db_handler, f"{_Q['LC']} {where_str}", tuple(base_params))
    total = count_res[0][0] if count_res else 0
    rows = execute_query(
        ctx.db_handler,
        f"{_Q['LB']} {where_str} ORDER BY s.sDate DESC LIMIT %s OFFSET %s",
        tuple(base_params + [limit, offset]),
    )
    items = [_row_to_session_item(row) for row in rows]
    return SessionListResponse(items=items, total=total, page=page, limit=limit)


# detail 1회가 반환하는 초 배치 상한. 무제한이면 장시간/방치 세션에서 수십만 프레임을
# 이벤트루프 위에서 직렬화하다 서버가 멎는다. 초과분은 truncated=true + fromSecSeq 페이징.
_DETAIL_MAX_SECS = 1800


def _get_session_detail_impl(
    ctx: AppContext,
    session_id: str,
    user_id: int,
    user_role: str | UserRole | None = None,
    from_sec_seq: int | None = None,
    to_sec_seq: int | None = None,
) -> SessionDetailResponse:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")
    session = _get_owned_session_row(ctx, session_id, user_id, user_role=user_role)

    where_parts = ["sId = %s"]
    params: list = [session_id]
    if from_sec_seq is not None:
        where_parts.append("secSeq >= %s")
        params.append(from_sec_seq)
    if to_sec_seq is not None:
        where_parts.append("secSeq <= %s")
        params.append(to_sec_seq)

    rows = execute_query(
        ctx.db_handler,
        _Q["SNAP"].format(where=" AND ".join(where_parts)),
        tuple(params + [_DETAIL_MAX_SECS + 1]),
    )
    truncated = len(rows) > _DETAIL_MAX_SECS
    rows = rows[:_DETAIL_MAX_SECS]

    # 초 배치들의 records를 하나의 평탄화 프레임 배열로 (admin SysDetail 소비 구조).
    # model_validate: 수신이 원형 저장한 extra 키를 그대로 보존한다.
    # 타 경로로 적재된 비정합 레코드 하나가 detail 전체를 500으로 만들지 않도록
    # 검증 실패 레코드는 건너뛴다 (원문은 rawPayload에 남아 있음).
    snapshots: list[SessionRecord] = []
    skipped = 0
    for row in rows:
        for rec in _extract_records(row[1]):
            try:
                snapshots.append(SessionRecord.model_validate(rec))
            except Exception:
                skipped += 1
    if skipped and ctx.log:
        ctx.log.warning(f"session/detail: skipped {skipped} malformed record(s) | sId={session_id}")

    return SessionDetailResponse(
        session=session,
        snapshots=snapshots,
        secCount=len(rows),
        recordCount=len(snapshots),
        truncated=truncated,
    )


def _start_session_impl(ctx: AppContext, payload: SessionStartRequest, user_id: int) -> SessionItem:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    img_rows = execute_query(ctx.db_handler, "SELECT id FROM tb_img WHERE id = %s", (payload.imgId,))
    if not img_rows:
        raise HTTPException(status_code=404, detail="Reference image not found")

    now = int(time.time())
    device_json = json.dumps(payload.device, ensure_ascii=False) if payload.device is not None else None
    conn = ctx.db_handler.get_connection()

    for _ in range(5):
        session_id = generate_sid()
        try:
            params = (
                session_id,
                user_id,
                payload.imgId,
                now,
                None,
                device_json,
                SessionStatus.READY.value,
                now,
                now,
            )
            with conn.cursor() as cursor:
                cursor.execute(_Q["SI"], params)
            conn.commit()
            return _get_session_row(ctx, session_id)
        except pymysql.err.IntegrityError as e:
            conn.rollback()
            if getattr(e, "args", None) and e.args[0] == 1062:
                continue
            if ctx.log:
                ctx.log.error(f"Failed to start session: {e}")
            raise HTTPException(status_code=500, detail="Failed to start session")
        except Exception as e:
            conn.rollback()
            if ctx.log:
                ctx.log.error(f"Failed to start session: {e}")
            raise HTTPException(status_code=500, detail="Failed to start session")

    raise HTTPException(status_code=503, detail="Could not allocate unique session ID")


def _end_session_impl(ctx: AppContext, payload: SessionEndRequest) -> dict:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    current = _get_session_row(ctx, payload.id)
    if current.sStat != SessionStatus.READY.value:
        raise HTTPException(status_code=409, detail="Session already closed")

    now = int(time.time())
    params = (now, SessionStatus.COMPLETED.value, now, payload.id)
    conn = ctx.db_handler.get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(_Q["SU"], params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        if ctx.log:
            ctx.log.error(f"Failed to end session: {e}")
        raise HTTPException(status_code=500, detail="Failed to end session")

    # v6 계약: end 응답에 세션 flush 결과 포함 (DB 직행이라 적재 현황 요약).
    # UPDATE는 이미 커밋됐으므로 이후 조회가 실패해도 500을 내면 안 된다 —
    # 500이면 앱이 재시도하고, 재시도는 sStat 가드의 409에 막혀 end 응답을 영영 못 받는다.
    try:
        base = _get_session_row(ctx, payload.id).model_dump()
    except Exception as e:
        if ctx.log:
            ctx.log.warning(f"session/end: post-commit fetch failed, degrading | sId={payload.id} | {e}")
        base = current.model_dump()
        base.update({"eDate": now, "sStat": SessionStatus.COMPLETED.value, "uDate": now})
    # snapshotCount는 방금 조회한 집계에 이미 있다 — 별도 COUNT 쿼리 불필요
    flush = {"sId": payload.id, "flushed": 0, "persistedSecs": base.get("snapshotCount") or 0}
    return {**base, "snapshotFlush": flush}


def _norm_filter(payload: SessionListRequest) -> tuple:
    z = payload.filter
    if z is not None and not any(v is not None for v in z.model_dump().values()):
        z = None

    def pick(name):
        return getattr(z, name) if z is not None else getattr(payload, name)

    return (
        pick("userId"),
        pick("imgId"),
        pick("sStat"),
        pick("sDate"),
        pick("eDate"),
        pick("category"),
        pick("feedback"),
        pick("stuckSec"),
        pick("canCapture"),
    )


def _invoke(ctx, op: str, payload, user: dict):
    if op == "L":
        user_id, img_id, s_stat, s_date, e_date, category, feedback, stuck_sec, can_capture = _norm_filter(payload)
        # 비-admin은 항상 본인 세션만 — list가 타인 텔레메트리 집계(mainFeedback 등)를
        # 노출하지 않도록 detail의 소유권 규칙과 대칭을 맞춘다
        if not _is_admin_role(user.get("role")):
            user_id = user.get("id")
        return _list_sessions_impl(
            ctx,
            page=payload.page,
            limit=payload.limit,
            user_id=user_id,
            img_id=img_id,
            s_stat=s_stat,
            sDate=s_date,
            eDate=e_date,
            category=category,
            feedback=feedback,
            stuck_sec=stuck_sec,
            can_capture=can_capture,
        )
    if op == "D":
        return _get_session_detail_impl(
            ctx,
            session_id=payload.id,
            user_id=user["id"],
            user_role=user.get("role"),
            from_sec_seq=payload.fromSecSeq,
            to_sec_seq=payload.toSecSeq,
        )
    if op == "S":
        return _start_session_impl(ctx, payload, user_id=user["id"])
    return _end_session_impl(ctx, payload)


@router.post("/list")
async def list_sessions(request: Request, payload: SessionListRequest, user=Depends(require_user)):
    """촬영 세션 목록 조회 (텔레메트리 집계·필터 포함, 비-admin은 본인 세션만)"""
    ctx = request.app.state.ctx
    result = _invoke(ctx, "L", payload, user)
    return build_success_response(result)


@router.post("/detail")
async def get_session_detail(request: Request, payload: SessionDetailRequest, user=Depends(require_user)):
    """세션 상세 조회 (+ 프레임 스냅샷 평탄화 배열)"""
    ctx = request.app.state.ctx
    result = _invoke(ctx, "D", payload, user)
    return build_success_response(result)


@router.post("/start")
async def start_session(request: Request, payload: SessionStartRequest, user=Depends(require_user)):
    """촬영 세션 시작"""
    ctx = request.app.state.ctx
    result = _invoke(ctx, "S", payload, user)
    return build_response_body(ResponseStatus.CREATED, result)


@router.post("/end")
async def end_session(request: Request, payload: SessionEndRequest, _=Depends(require_user)):
    """촬영 세션 종료 (응답 data.snapshotFlush 포함)"""
    ctx = request.app.state.ctx
    result = _invoke(ctx, "E", payload, {})

    return build_success_response(result)
