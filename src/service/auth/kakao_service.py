# 카카오 로그인: 카카오가 발급한 액세스 토큰을 검증하고 우리 회원으로 연결한다.
#
# 흐름 (모바일 SDK 방식):
#   iOS 앱이 카카오 SDK로 로그인 → 받은 카카오 액세스 토큰을 서버로 전달
#   → 서버가 카카오 API로 토큰 검증 (우리 앱에서 발급된 토큰인지 app_id 대조 포함)
#   → provider="kakao" + providerId(카카오 회원번호)로 기존 회원 조회, 없으면 자동 가입
#   → 이후는 이메일 로그인과 동일하게 자체 JWT 발급 (auth_api에서 처리)

import uuid
from typing import Tuple

import httpx
from fastapi import HTTPException

from src.app_context import AppContext
from src.service.auth import auth_service
from src.service.auth.auth_schema import UserCreate

_KAPI_BASE = "https://kapi.kakao.com"
_TIMEOUT_SECONDS = 10.0

# 카카오가 이메일을 안 주는 경우(동의 안 함·비즈 앱 미전환)에 쓰는 합성 이메일 도메인.
# example.com은 IANA 영구 예약 도메인이라 실제 메일함이 존재할 수 없고,
# EmailStr 형식 검증은 통과한다. (.local/.invalid는 검증기가 거부하므로 쓸 수 없음)
_SYNTHETIC_EMAIL_DOMAIN = "kakao-user.example.com"


async def _kakao_get(path: str, access_token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{_KAPI_BASE}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"카카오 서버와 통신에 실패했습니다 ({type(e).__name__})")

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 카카오 토큰입니다")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"카카오 API 오류 (HTTP {resp.status_code})")
    return resp.json()


def _resolve_nickname(ctx, raw: str, provider_id: str) -> str:
    """카카오 닉네임을 서비스 규칙(2~10자, 중복 불가)에 맞춘다.

    - 10자 초과면 자르고, 2자 미만/없음이면 "카카오XXXX" 폴백
    - 이미 쓰는 닉네임이면 뒤에 숫자를 붙여 비는 값을 찾는다 (카카오 가입이
      닉네임 중복 때문에 실패하지 않도록)
    """
    base = (raw or "").strip()[:10]
    if len(base) < 2:
        base = f"카카오{provider_id[-4:]}"[:10]
    if not auth_service.check_nickname_exists(ctx, base):
        return base
    for i in range(2, 100):
        suffix = str(i)
        candidate = f"{base[:10 - len(suffix)]}{suffix}"
        if not auth_service.check_nickname_exists(ctx, candidate):
            return candidate
    return uuid.uuid4().hex[:10]  # 사실상 도달 불가한 최후 폴백


async def authenticate_kakao_user(ctx: AppContext, access_token: str) -> Tuple[dict, bool]:
    """카카오 액세스 토큰을 검증하고 (회원 dict, 신규 가입 여부)를 반환한다."""
    # 1) 토큰 검증 + 발급 앱 대조 (설정에 kakao.app_id가 있을 때만 대조)
    token_info = await _kakao_get("/v1/user/access_token_info", access_token)
    expected_app_id = ctx.cfg.kakao.app_id if ctx.cfg.kakao else None
    if expected_app_id and token_info.get("app_id") != expected_app_id:
        raise HTTPException(status_code=401, detail="다른 앱에서 발급된 카카오 토큰입니다")

    # 2) 카카오 프로필 조회
    me = await _kakao_get("/v2/user/me", access_token)
    kakao_id = me.get("id")
    if not kakao_id:
        raise HTTPException(status_code=502, detail="카카오 응답에 회원번호가 없습니다")
    provider_id = str(kakao_id)

    # 3) 기존 회원이면 그대로 반환
    user = auth_service.get_user_by_provider(ctx, "kakao", provider_id)
    if user:
        return user, False

    # 4) 신규 자동 가입
    account = me.get("kakao_account") or {}
    profile = account.get("profile") or {}
    raw_nickname = (
        profile.get("nickname")
        or (me.get("properties") or {}).get("nickname")
        or ""
    )
    nickname = _resolve_nickname(ctx, raw_nickname, provider_id)

    # 이메일은 (동의로 받았고 + 검증됐고 + 미사용일 때)만 실제 값을 쓴다.
    # 같은 이메일의 기존 계정에 자동으로 붙이지 않는 이유: 카카오 토큰만으로
    # 타인 계정을 점유하는 계정 탈취 경로가 되기 때문 (연동은 추후 별도 기능으로).
    email = account.get("email")
    email_usable = (
        bool(email)
        and bool(account.get("is_email_valid"))
        and bool(account.get("is_email_verified"))
        and not auth_service.check_email_exists(ctx, email)
    )
    if email_usable:
        email_conf = "1"
    else:
        email = f"kakao_{provider_id}@{_SYNTHETIC_EMAIL_DOMAIN}"
        email_conf = "2"

    dto = UserCreate(
        name=nickname,
        nickname=nickname,
        email=email,
        emailConf=email_conf,
        provider="kakao",
        providerId=provider_id,
        password=None,  # 소셜 로그인 계정은 비밀번호 없음 (tb_user.password NULL 허용)
        agreeTerms=True,
    )
    created = auth_service.create_user(ctx, dto)
    ctx.log.info(f"Kakao signup | userId={created['id']} providerId={provider_id}")
    return created, True
