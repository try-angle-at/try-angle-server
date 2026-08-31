from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Optional, Any
import threading
import uuid

import aioboto3
from fastapi import UploadFile, HTTPException

from src.service.files.files_schema import (
    FileMetadata,
    IMAGE_MAX_BYTES,
    ALLOWED_CONTENT_TYPES,
    ALLOWED_UPLOAD_TYPES,
    UPLOAD_CONFIG,
)


_STORE: Dict[str, FileMetadata] = {}
_STORE_LOCK = threading.Lock()


def _storage_client(ctx):
    """오브젝트 스토리지 클라이언트.

    - storage.endpoint_url이 비어 있으면 AWS S3: 자격증명은 boto3 기본 체인
      (EC2 인스턴스 프로파일 IAM Role — 키를 설정에 두지 않는다)
    - 설정되어 있으면 Cloudflare R2 등 S3 호환 스토리지: 액세스 키 필요
    """
    st = ctx.cfg.storage
    session = aioboto3.Session()
    kwargs = {"region_name": st.region}
    if st.endpoint_url:
        kwargs["endpoint_url"] = st.endpoint_url
        kwargs["aws_access_key_id"] = st.access_key_id
        kwargs["aws_secret_access_key"] = st.secret_access_key
    return session.client("s3", **kwargs)


async def save_file(
    ctx,
    file: UploadFile,
    meta: Optional[Dict[str, Any]] = None,
    upload_type: Optional[str] = None,
    user_id: Optional[int] = None,
) -> FileMetadata:
    # --- 유효성 검사 ---
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{content_type}'. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}",
        )

    data = await file.read()
    if len(data) > IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large ({len(data)} bytes). Max allowed: {IMAGE_MAX_BYTES} bytes (10 MB)",
        )

    # --- 스토리지 업로드 ---
    st_cfg = ctx.cfg.storage
    if not upload_type:
        raise HTTPException(status_code=400, detail="'type' is required")

    upload_type = upload_type.strip().lower()
    if upload_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid type '{upload_type}'. Allowed: {sorted(ALLOWED_UPLOAD_TYPES)}",
        )

    upload_cfg = UPLOAD_CONFIG[upload_type]
    folder = upload_cfg["path"].strip("/")
    file_id = uuid.uuid4().hex
    safe_name = Path(file.filename or "upload.bin").name
    ext = Path(safe_name).suffix.lower()
    if not ext:
        ext = ".bin"

    now = int(time.time())
    tm = time.gmtime(now)

    if upload_cfg.get("useDatePath"):
        folder = f"{folder}/{tm.tm_year}/{tm.tm_mon:02d}"

    if upload_type in ("snap", "capture"):
        if user_id is None:
            raise HTTPException(status_code=400, detail="user id is required for this upload type")
        id_part = f"u{user_id}"
    else:
        id_part = uuid.uuid4().hex[:8]

    key = f"{folder}/{upload_cfg['prefix']}{id_part}_{now}{ext}"

    async with _storage_client(ctx) as client:
        await client.put_object(
            Bucket=st_cfg.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    base_url = (st_cfg.public_base_url or "").rstrip("/")
    public_url = f"{base_url}/{key}"

    metadata = FileMetadata(
        fileId=file_id,
        fileName=safe_name,
        fileKey=key,
        url=public_url,
        size=len(data),
        contentType=content_type,
        meta=meta or {},
        cDate=now,
        uDate=now,
    )

    with _STORE_LOCK:
        _STORE[file_id] = metadata

    ctx.log.info(f"Uploaded to storage | id={file_id} key={key} size={len(data)}")
    return metadata


async def delete_file(ctx, file_id: str) -> Optional[FileMetadata]:
    with _STORE_LOCK:
        info = _STORE.pop(file_id, None)

    if not info:
        return None

    try:
        async with _storage_client(ctx) as client:
            await client.delete_object(
                Bucket=ctx.cfg.storage.bucket_name,
                Key=info.fileKey,
            )
    except Exception as e:
        ctx.log.warning(f"Failed to delete from storage | id={file_id} | err={e}")

    ctx.log.info(f"Deleted from storage | id={file_id}")
    return info


def get_file(file_id: str) -> Optional[FileMetadata]:
    with _STORE_LOCK:
        return _STORE.get(file_id)


def list_files() -> list[FileMetadata]:
    with _STORE_LOCK:
        return list(_STORE.values())


async def get_presigned_url(ctx, file_id: str) -> Optional[str]:
    with _STORE_LOCK:
        info = _STORE.get(file_id)
    if not info:
        return None

    st_cfg = ctx.cfg.storage
    async with _storage_client(ctx) as client:
        url = await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": st_cfg.bucket_name, "Key": info.fileKey},
            ExpiresIn=st_cfg.upload_url_expire_seconds,
        )
    return url
