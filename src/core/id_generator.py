# src/core/id_generator.py
# 세션 ID 생성 유틸 (원본 모듈이 레포에 누락되어 최소 구현으로 복원)

import uuid


def generate_sid() -> str:
    """tb_session.id (VARCHAR(32)) 에 맞는 32자 16진수 랜덤 ID를 반환한다.

    호출부(session_api)는 PK 충돌 시 최대 5회 재시도하므로 순수 랜덤이면 충분하다.
    """
    return uuid.uuid4().hex
