from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
}

UPLOAD_CONFIG = {
    "profile": {
        "path": "profiles/",
        "prefix": "p_",
    },
    "prod": {
        "path": "prod/",
        "prefix": "prod_",
    },
    "reference": {
        "path": "reference/",
        "prefix": "ref_",
    },
    "snap": {
        "path": "snaps/",  # 여기에 YYYY/MM은 동적으로 추가
        "prefix": "snap_",
        "useDatePath": True,
    },
    "capture": {
        "path": "captures/",  # 일반 촬영 결과 (3모드 계약) — YYYY/MM 동적 추가
        "prefix": "cap_",
        "useDatePath": True,
    },
    "temp": {
        "path": "temp/",
        "prefix": "tmp_",
    },
}

ALLOWED_UPLOAD_TYPES = set(UPLOAD_CONFIG.keys())

class FileMetadata(BaseModel):
    fileId: str
    fileName: str
    fileKey: str
    url: str
    size: int
    contentType: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    cDate: int
    uDate: int


class FileListResponse(BaseModel):
    files: list[FileMetadata]
    total: int


class FileIdRequest(BaseModel):
    fileId: str = Field(..., description="파일 ID")
