from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# DB 컬럼이 받는 범위만 제약한다 (secSeq→INT, tid→BIGINT 파생 sDate/eDate).
# 범위 밖 값이 pydantic을 통과하면 MySQL 1264로 500이 나고, 앱은 같은 배치를
# 재시도하므로 그 초가 영구 유실된다 — 422로 즉시 거부하는 쪽이 계약에 안전.
_INT_MAX = 2_147_483_647
_BIGINT_MAX = 9_223_372_036_854_775_807


class TelemetryFrame(BaseModel):
    """v6 텔레메트리 프레임 1개.

    시퀀싱 필드(fseq/tid/offsetMs)만 타입 검증하고, 본문(cur/res 및 그 외 키)은
    무검증으로 통과시켜 rawPayload에 그대로 저장한다 (v6 "봉투 고정 + 본문 자유" 원칙).

    주의: gate에 상한 제약(le=...)을 걸지 않는다. 6/25에 le=5 제약으로
    실기기 전송이 전부 400 난 사고 전례가 있음 (SDK docs/backend-gate-le5-request.md).
    gate 값 범위(현재 0~8)는 문서로만 관리한다.
    """

    model_config = ConfigDict(extra="allow")

    fseq: int = Field(..., description="세션 전역 프레임 번호 (초를 넘어 연속)")
    tid: int = Field(..., ge=0, le=_BIGINT_MAX, description="프레임 절대시각 unix ms (정수만 허용)")
    offsetMs: int = Field(..., description="해당 초 내 경과 ms (매 초 첫 프레임에서 0 리셋)")
    gate: Optional[int] = Field(None, description="게이트 번호 (옵션, 상한 제약 금지)")
    phase: Optional[str] = Field(None, description="촬영 단계 (예: CAMERA_ADJUST)")
    pidx: Optional[int] = Field(None, description="단계 인덱스 (구 호환: gate와 동일)")
    cur: Optional[dict[str, Any]] = Field(None, description="현재 상태 (무검증 통과)")
    res: Optional[dict[str, Any]] = Field(None, description="판정 결과 (무검증 통과)")


class SystemSendRequest(BaseModel):
    """1초 = 1배치. 활성 추적 ~30fps, 미검출 시 1fps라 프레임 수는 1~30 가변.

    payload 상한 300은 계약(1~30)의 10배 여유 — fps 정책이 바뀌어도 통과하되,
    폭주 클라이언트의 수십만 프레임 배치(파싱 부하 + max_allowed_packet 초과)는 차단.
    """

    sId: str = Field(..., description="세션 ID (session/start 응답 data.id)")
    secSeq: int = Field(..., ge=1, le=_INT_MAX, description="세션 N번째 초 (1부터 증가)")
    payload: list[TelemetryFrame] = Field(
        ..., min_length=1, max_length=300,
        description="그 초의 프레임 목록 (offsetMs 오름차순, 1~30 계약 + 여유)",
    )


class SystemFlushSecRequest(BaseModel):
    sId: str = Field(..., description="세션 ID")
    secSeq: int = Field(..., ge=1, le=_INT_MAX, description="확정할 초 번호")


class SystemFlushSessionRequest(BaseModel):
    sId: str = Field(..., description="세션 ID")
