from typing import Any, Optional

from pydantic import BaseModel, Field

# DB 컬럼 범위만 제약 (범위 밖은 500 대신 422 — 앱 재시도 루프 방지)
_BIGINT_MAX = 9_223_372_036_854_775_807


class CaptureCreateRequest(BaseModel):
    """일반 촬영 결과 등록 (3모드 계약 §3-2).

    mode는 하드 enum 없이 VARCHAR(16) 저장 — 알려진 값: aesthetic_ref | direct | ai_director.
    한 direct 세션 안에 direct 사진과 ai_director 사진이 섞이는 것이 정상이다.
    """
    sId: Optional[str] = Field(None, max_length=32, description="촬영 세션 ID (텔레메트리 조인 키, 본인 세션만)")
    imgId: Optional[int] = Field(None, description="레퍼런스 ID (aesthetic_ref일 때)")
    mode: str = Field(..., min_length=1, max_length=16, description="촬영 순간 유효 상태: aesthetic_ref | direct | ai_director")
    captureUrl: str = Field(..., min_length=1, max_length=500, description="사진 경로 — files/create(type=capture)의 url/fileKey")
    capturedAt: int = Field(..., ge=0, le=_BIGINT_MAX, description="촬영 시각 unix ms")
    analysis: Optional[dict[str, Any]] = Field(None, description="촬영 순간 판정 요약 — 무검증 JSON 통과 (스키마는 SDK 소유)")


class CaptureGetRequest(BaseModel):
    id: int = Field(..., description="캡처 ID")


class CaptureDeleteRequest(BaseModel):
    id: int = Field(..., description="캡처 ID")


class CaptureListFilter(BaseModel):
    userId: Optional[int] = Field(None, description="사용자 ID 필터 (admin 전용 — 비-admin은 본인 강제)")
    mode: Optional[str] = Field(None, max_length=16, description="촬영 모드 필터")
    imgId: Optional[int] = Field(None, description="레퍼런스 ID 필터")
    sId: Optional[str] = Field(None, max_length=32, description="세션 ID 필터")
    fromDate: Optional[int] = Field(None, ge=0, description="capturedAt 시작 (unix ms)")
    toDate: Optional[int] = Field(None, ge=0, description="capturedAt 종료 (unix ms)")


class CaptureListRequest(BaseModel):
    page: int = Field(1, ge=1, description="페이지 번호")
    limit: int = Field(20, ge=1, le=100, description="페이지 크기")
    filter: Optional[CaptureListFilter] = Field(None, description="목록 필터")
    sortBy: str = Field("capturedAt", description="정렬 컬럼 (capturedAt, cDate, id)")
    sortOrder: str = Field("desc", description="정렬 방향 (asc, desc)")

    # 하위 호환: flat body 지원 (snap/session과 동일 관례)
    userId: Optional[int] = Field(None, description="사용자 ID 필터")
    mode: Optional[str] = Field(None, max_length=16, description="촬영 모드 필터")
    imgId: Optional[int] = Field(None, description="레퍼런스 ID 필터")
    sId: Optional[str] = Field(None, max_length=32, description="세션 ID 필터")
    fromDate: Optional[int] = Field(None, ge=0, description="capturedAt 시작 (unix ms)")
    toDate: Optional[int] = Field(None, ge=0, description="capturedAt 종료 (unix ms)")


class CaptureItem(BaseModel):
    id: int
    userId: int
    userName: Optional[str] = None
    sId: Optional[str] = None
    imgId: Optional[int] = None
    mode: str
    captureUrl: str
    analysis: Optional[dict[str, Any]] = None
    capturedAt: int
    cDate: int
    uDate: int

    class Config:
        from_attributes = True


class CaptureListResponse(BaseModel):
    items: list[CaptureItem]
    total: int
    page: int
    limit: int

    class Config:
        from_attributes = True
