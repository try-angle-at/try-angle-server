import json
import time

from fastapi import HTTPException

from src.app_context import AppContext
from src.utils.db_utils import execute_query
from src.service.system.system_schema import SystemSendRequest, TelemetryFrame

# 6월 배포 서버는 RabbitMQ+Redis 버퍼를 거쳐 tb_rt_snapshot에 적재했으나,
# SDK 팀 확인 결과 "HTTP 계약만 동일하면 DB 직행 무방"이라 큐 없이 바로 저장한다.
# 따라서 flushSec/flushSession은 버퍼 확정이 아니라 적재 현황 응답으로 동작한다(멱등).

_UPSERT_SQL = """
    INSERT INTO tb_rt_snapshot
        (sId, secSeq, sDate, eDate, category, feedback, stuckSec, canCapture, rawPayload, cDate)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        sDate = VALUES(sDate),
        eDate = VALUES(eDate),
        category = VALUES(category),
        feedback = VALUES(feedback),
        stuckSec = VALUES(stuckSec),
        canCapture = VALUES(canCapture),
        rawPayload = VALUES(rawPayload)
"""
# ON DUPLICATE KEY: 앱이 네트워크 오류로 같은 secSeq 배치를 재전송해도 안전(멱등).


def _ensure_session_exists(ctx: AppContext, session_id: str) -> None:
    rows = execute_query(ctx.db_handler, "SELECT id FROM tb_session WHERE id = %s", (session_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Session not found")


def _derive_batch_summary(frames: list[TelemetryFrame]) -> tuple:
    """session/list 필터가 컬럼으로 직접 조회하는 요약값을 배치에서 도출한다.

    (22224a6 복원 코드가 rt.category/feedback/stuckSec/canCapture 컬럼을 참조)
    - category/feedback: 배치 내 마지막으로 값이 있던 프레임 기준 (그 초의 최종 상태)
    - stuckSec: 배치 내 최대값 (세션 집계가 MAX(rt.stuckSec)이므로 배치도 max)
    - canCapture: 배치 내 한 프레임이라도 true면 'true' ("그 초에 촬영 가능했나")
    """
    category = None
    feedback = None
    stuck_max = None
    can_capture = None

    for frame in frames:
        res = frame.res or {}
        if res.get("category") is not None:
            category = str(res["category"])
        if res.get("feedback") is not None:
            feedback = str(res["feedback"])

        meta = res.get("metadata") or {}
        stuck = meta.get("stuckSec")
        if isinstance(stuck, (int, float)):
            stuck_max = stuck if stuck_max is None else max(stuck_max, stuck)

        cc = meta.get("canCapture")
        if cc is not None:
            if cc is True or str(cc).lower() == "true":
                can_capture = "true"
            elif can_capture is None:
                can_capture = "false"

    return category, feedback, stuck_max, can_capture


def save_batch(ctx: AppContext, payload: SystemSendRequest) -> dict:
    """1초 배치를 tb_rt_snapshot 1행으로 저장한다."""
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    _ensure_session_exists(ctx, payload.sId)

    frames = payload.payload
    tids = [f.tid for f in frames]
    s_date = min(tids) if tids else None
    e_date = max(tids) if tids else None
    category, feedback, stuck_max, can_capture = _derive_batch_summary(frames)

    # 복원한 조회 코드(_extract_records)가 rawPayload["records"] 형태를 기대하므로 맞춘다.
    # exclude_unset: 클라이언트가 실제로 보낸 필드만 저장 (본문 원형 보존)
    raw = {"records": [f.model_dump(exclude_unset=True) for f in frames]}

    now = int(time.time())
    params = (
        payload.sId,
        payload.secSeq,
        s_date,
        e_date,
        category,
        feedback,
        stuck_max,
        can_capture,
        json.dumps(raw, ensure_ascii=False),
        now,
    )

    conn = ctx.db_handler.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(_UPSERT_SQL, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        if ctx.log:
            ctx.log.error(f"Failed to save telemetry batch: sId={payload.sId} secSeq={payload.secSeq} | {e}")
        raise HTTPException(status_code=500, detail="Failed to save telemetry batch")

    return {
        "sId": payload.sId,
        "secSeq": payload.secSeq,
        "frameCount": len(frames),
        "stored": True,
    }


def flush_sec(ctx: AppContext, session_id: str, sec_seq: int) -> dict:
    """DB 직행 구조라 버퍼가 없다. 해당 초의 적재 여부만 확인해 응답한다(멱등)."""
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    _ensure_session_exists(ctx, session_id)
    rows = execute_query(
        ctx.db_handler,
        "SELECT COUNT(*) FROM tb_rt_snapshot WHERE sId = %s AND secSeq = %s",
        (session_id, sec_seq),
    )
    persisted = bool(rows and rows[0][0] > 0)
    return {"sId": session_id, "secSeq": sec_seq, "flushed": 0, "persisted": persisted}


def flush_session_summary(ctx: AppContext, session_id: str) -> dict:
    """세션 전체 적재 현황. session/end의 data.snapshotFlush에도 그대로 쓰인다."""
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    rows = execute_query(
        ctx.db_handler,
        "SELECT COUNT(*) FROM tb_rt_snapshot WHERE sId = %s",
        (session_id,),
    )
    persisted_secs = rows[0][0] if rows else 0
    return {"sId": session_id, "flushed": 0, "persistedSecs": persisted_secs}


def flush_session(ctx: AppContext, session_id: str) -> dict:
    _ensure_session_exists(ctx, session_id)
    return flush_session_summary(ctx, session_id)
