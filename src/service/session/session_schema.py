from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SessionStatus(IntEnum):
    READY = 0
    COMPLETED = 1
    AUTO_TERM = 2
    FAILED = 3


class SessionStartRequest(BaseModel):
    imgId: int = Field(..., description="레퍼런스 이미지 ID")
    device: Optional[dict[str, Any]] = Field(None, description="디바이스 메타데이터")


class SessionEndRequest(BaseModel):
    id: str = Field(..., description="세션 ID")


class SessionListFilter(BaseModel):
    userId: Optional[int] = Field(None, description="사용자 ID 필터")
    imgId: Optional[int] = Field(None, description="레퍼런스 이미지 ID 필터")
    sStat: Optional[int] = Field(None, description="세션 상태 필터")
    sDate: Optional[int] = Field(None, description="시작일(from) Unix Timestamp")
    eDate: Optional[int] = Field(None, description="시작일(to) Unix Timestamp")
    # 실시간 스냅샷(tb_rt_snapshot) 기반 필터 — admin SysList가 전송
    category: Optional[str] = Field(None, description="판정 카테고리 필터 (예: pitch, pose)")
    feedback: Optional[str] = Field(None, description="가이드 피드백 문구 검색 (부분 일치)")
    stuckSec: Optional[int] = Field(None, ge=0, description="최소 정체 시간(초) 조건")
    canCapture: Optional[str] = Field(None, description="촬영 가능 여부 필터 ('true' 또는 'false')")


class SessionListRequest(BaseModel):
    page: int = Field(1, ge=1, description="페이지 번호")
    limit: int = Field(20, ge=1, le=100, description="페이지 크기")
    filter: Optional[SessionListFilter] = Field(None, description="목록 필터")

    # 하위 호환: 기존 flat body 지원
    userId: Optional[int] = Field(None, description="사용자 ID 필터")
    imgId: Optional[int] = Field(None, description="레퍼런스 이미지 ID 필터")
    sStat: Optional[int] = Field(None, description="세션 상태 필터")
    sDate: Optional[int] = Field(None, description="시작일(from) Unix Timestamp")
    eDate: Optional[int] = Field(None, description="시작일(to) Unix Timestamp")
    category: Optional[str] = Field(None, description="판정 카테고리 필터")
    feedback: Optional[str] = Field(None, description="가이드 피드백 문구 검색")
    stuckSec: Optional[int] = Field(None, ge=0, description="최소 정체 시간(초) 조건")
    canCapture: Optional[str] = Field(None, description="촬영 가능 여부 필터")


class SessionDetailRequest(BaseModel):
    id: str = Field(..., description="세션 ID")
    fromSecSeq: Optional[int] = Field(None, ge=1, description="secSeq 시작 필터")
    toSecSeq: Optional[int] = Field(None, ge=1, description="secSeq 종료 필터")


class SessionItem(BaseModel):
    id: str
    userId: int
    userName: Optional[str] = None
    imgId: int
    sDate: int
    eDate: Optional[int] = None
    device: Optional[dict[str, Any]] = None
    sStat: int
    cDate: int
    uDate: int
    # 텔레메트리 집계 필드 (tb_rt_snapshot 서브쿼리)
    maxStuckSec: Optional[float] = Field(None, description="세션 내 최대 정체 시간(초)")
    snapshotCount: Optional[int] = Field(None, description="적재된 초 배치 수")
    mainFeedback: Optional[str] = Field(None, description="마지막 가이드 피드백 메시지")

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    items: list[SessionItem]
    total: int
    page: int
    limit: int

    class Config:
        from_attributes = True


class SessionRecord(BaseModel):
    """detail 응답의 프레임 1개 (v6 payload 프레임 평탄화).

    저장 데이터에 필드가 없을 수 있으므로 전부 Optional — 특히 gate는
    상한 제약은 물론 필수 강제도 하지 않는다 (le=5 사고 전례).
    """
    tid: Optional[int] = None
    fseq: Optional[int] = None
    offsetMs: Optional[int] = None
    gate: Optional[int] = None
    phase: Optional[str] = None
    pidx: Optional[int] = None
    cur: Optional[dict[str, Any]] = None
    res: Optional[dict[str, Any]] = None

    class Config:
        from_attributes = True


class SessionDetailResponse(BaseModel):
    session: SessionItem
    # secSeq 오름차순 → 각 배치의 records를 이어붙인 평탄화 프레임 배열
    snapshots: list[SessionRecord] = Field(default_factory=list)
    secCount: int = Field(0, description="적재된 초 배치 수")
    recordCount: int = Field(0, description="프레임 총수")

    class Config:
        from_attributes = True
