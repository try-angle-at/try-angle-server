import math


def sanitize_json(value):
    """NaN/Infinity를 None으로 치환한다.

    FastAPI 기본 파서는 bare NaN 토큰을 받아들이지만 json.dumps가 그대로 방출하면
    MySQL JSON 컬럼이 거부(3140)해 해당 요청이 영구 실패한다 — 저장 전에 소독한다.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_json(v) for v in value]
    return value
