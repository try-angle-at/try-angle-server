import json
import time

from fastapi import HTTPException

from src.app_context import AppContext
from src.service.reference.reference_schema import (
    RefCategory,
    RefCreateRequest,
    RefItem,
    RefListItem,
    RefListResponse,
    RefListUser,
    RefUpdateRequest,
    RefUser,
)
from src.utils.db_utils import execute_query


def _parse_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def _row_to_ref_item(row: tuple) -> RefItem:
    return RefItem(
        imgId=row[0],
        user=RefUser(userId=row[1], nickname=row[2], fileUrl=row[3]),
        ctg=RefCategory(ctgId=row[4], ctgName=row[5]),
        imgUrl=row[6],
        title=row[7],
        desc=row[8],
        useCnt=row[9],
        kwd=_parse_json_field(row[10], []),
        aiDoc=_parse_json_field(row[11], None),
        expWeight=row[12],
        pri=row[13],
        cDate=row[14],
        uDate=row[15],
    )


def _row_to_ref_list_item(row: tuple) -> RefListItem:
    return RefListItem(
        imgId=row[0],
        user=RefListUser(userId=row[1], nickname=row[2]),
        ctg=RefCategory(ctgId=row[3], ctgName=row[4]),
        imgUrl=row[5],
        title=row[6],
        useCnt=row[7],
        kwd=_parse_json_field(row[8], []),
        expWeight=row[9],
        pri=row[10],
        cDate=row[11],
        uDate=row[12],
    )


def _ensure_ctg_exists(ctx: AppContext, ctg_id: int) -> None:
    rows = execute_query(ctx.db_handler, "SELECT id FROM tb_img_ctg WHERE id = %s", (ctg_id,))
    if not rows:
        raise HTTPException(status_code=400, detail="Category not found")


def list_refs(
    ctx: AppContext,
    page: int = 1,
    limit: int = 20,
    ctg_id: int | None = None,
    title: str | None = None,
    kwd: list | None = None,
    kwd_groups: list[list] | None = None,
    kwd_missing: list | None = None,
) -> RefListResponse:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    where_conditions: list[str] = []
    where_params: list = []
    if ctg_id is not None:
        where_conditions.append("i.ctgId = %s")
        where_params.append(ctg_id)
    if title is not None and title.strip() != "":
        where_conditions.append("i.title LIKE %s")
        where_params.append(f"%{title.strip()}%")
    if kwd:
        where_conditions.append("JSON_OVERLAPS(i.kwd, CAST(%s AS JSON))")
        where_params.append(json.dumps(kwd, ensure_ascii=False))
    # 축별 필터: 그룹 안은 OR(JSON_OVERLAPS), 그룹 사이는 AND —
    # 예: [[DOMAIN_*...], [SHOT_*...]] → "도메인 중 하나" AND "촬영방식 중 하나"
    for group in kwd_groups or []:
        if group:
            where_conditions.append("JSON_OVERLAPS(i.kwd, CAST(%s AS JSON))")
            where_params.append(json.dumps(group, ensure_ascii=False))
    # 미분류 큐: 지정 코드가 하나도 없는(또는 kwd 자체가 없는) 사진만.
    # kwd가 NULL이면 JSON_OVERLAPS가 NULL이 되어 NOT에서도 걸러지므로 IS NULL을 함께 허용한다.
    if kwd_missing:
        where_conditions.append("(i.kwd IS NULL OR NOT JSON_OVERLAPS(i.kwd, CAST(%s AS JSON)))")
        where_params.append(json.dumps(kwd_missing, ensure_ascii=False))

    where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
    where_params_tuple = tuple(where_params)

    count_sql = f"SELECT COUNT(*) FROM tb_img i {where_clause}"
    count_rows = execute_query(ctx.db_handler, count_sql, where_params_tuple)
    total = count_rows[0][0] if count_rows else 0

    list_sql = f"""
        SELECT
            i.id,
            i.userId,
            u.nickname,
            i.ctgId,
            c.name,
            i.imgUrl,
            i.title,
            i.useCnt,
            i.kwd,
            i.expWeight,
            i.pri,
            i.cDate,
            i.uDate
        FROM tb_img i
        INNER JOIN tb_user u ON u.id = i.userId
        INNER JOIN tb_img_ctg c ON c.id = i.ctgId
        {where_clause}
        ORDER BY i.cDate DESC
    """

    if page == 0:
        rows = execute_query(ctx.db_handler, list_sql, where_params_tuple)
    else:
        offset = (page - 1) * limit
        rows = execute_query(
            ctx.db_handler,
            f"{list_sql}\n        LIMIT %s OFFSET %s",
            where_params_tuple + (limit, offset),
        )

    items = [_row_to_ref_list_item(row) for row in rows]
    return RefListResponse(items=items, total=total, page=page, limit=limit)


def get_ref(ctx: AppContext, img_id: int) -> RefItem:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    sql = """
        SELECT
            i.id,
            i.userId,
            u.nickname,
            u.fileId,
            i.ctgId,
            c.name,
            i.imgUrl,
            i.title,
            i.`desc`,
            i.useCnt,
            i.kwd,
            i.aiDoc,
            i.expWeight,
            i.pri,
            i.cDate,
            i.uDate
        FROM tb_img i
        INNER JOIN tb_user u ON u.id = i.userId
        INNER JOIN tb_img_ctg c ON c.id = i.ctgId
        WHERE i.id = %s
    """
    rows = execute_query(ctx.db_handler, sql, (img_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Reference image not found")
    return _row_to_ref_item(rows[0])


def create_ref(ctx: AppContext, payload: RefCreateRequest, user_id: int) -> RefItem:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    _ensure_ctg_exists(ctx, payload.ctgId)

    now = int(time.time())
    kwd_json = json.dumps(payload.kwd, ensure_ascii=False) if payload.kwd is not None else None
    ai_doc_json = json.dumps(payload.aiDoc, ensure_ascii=False) if payload.aiDoc is not None else None

    sql = """
        INSERT INTO tb_img (userId, ctgId, imgUrl, title, `desc`, useCnt, kwd, aiDoc, expWeight, pri, cDate, uDate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        user_id,
        payload.ctgId,
        payload.imgUrl,
        payload.title,
        payload.desc,
        0,
        kwd_json,
        ai_doc_json,
        payload.expWeight,
        payload.pri,
        now,
        now,
    )

    conn = ctx.db_handler.get_connection()
    new_id: int | None = None
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            new_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        if ctx.log:
            ctx.log.error(f"Failed to create reference image: {e}")
        raise HTTPException(status_code=500, detail="Failed to create reference image")

    return get_ref(ctx, new_id)


def update_ref(ctx: AppContext, payload: RefUpdateRequest) -> RefItem:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    exists = execute_query(ctx.db_handler, "SELECT id FROM tb_img WHERE id = %s", (payload.id,))
    if not exists:
        raise HTTPException(status_code=404, detail="Reference image not found")

    fields = []
    params = []

    if payload.ctgId is not None:
        _ensure_ctg_exists(ctx, payload.ctgId)
        fields.append("ctgId = %s")
        params.append(payload.ctgId)
    if payload.imgUrl is not None:
        fields.append("imgUrl = %s")
        params.append(payload.imgUrl)
    if payload.title is not None:
        fields.append("title = %s")
        params.append(payload.title)
    if payload.desc is not None:
        fields.append("`desc` = %s")
        params.append(payload.desc)
    if payload.useCnt is not None:
        fields.append("useCnt = %s")
        params.append(payload.useCnt)
    if payload.kwd is not None:
        fields.append("kwd = %s")
        params.append(json.dumps(payload.kwd, ensure_ascii=False))
    if payload.aiDoc is not None:
        fields.append("aiDoc = %s")
        params.append(json.dumps(payload.aiDoc, ensure_ascii=False))
    if payload.expWeight is not None:
        fields.append("expWeight = %s")
        params.append(payload.expWeight)
    if payload.pri is not None:
        fields.append("pri = %s")
        params.append(payload.pri)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    now = int(time.time())
    fields.append("uDate = %s")
    params.append(now)
    params.append(payload.id)

    sql = f"UPDATE tb_img SET {', '.join(fields)} WHERE id = %s"
    conn = ctx.db_handler.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        if ctx.log:
            ctx.log.error(f"Failed to update reference image: {e}")
        raise HTTPException(status_code=500, detail="Failed to update reference image")

    return get_ref(ctx, payload.id)


def delete_ref(ctx: AppContext, img_id: int) -> dict:
    if not ctx.db_handler:
        raise HTTPException(status_code=500, detail="Database not initialized")

    rows = execute_query(ctx.db_handler, "SELECT id FROM tb_img WHERE id = %s", (img_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Reference image not found")

    conn = ctx.db_handler.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM tb_img WHERE id = %s", (img_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        if ctx.log:
            ctx.log.error(f"Failed to delete reference image: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete reference image")

    return {"id": img_id, "deleted": True}
