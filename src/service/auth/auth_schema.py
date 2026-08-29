from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, field_validator

# 한국 휴대폰 번호 (01X + 7~8자리, 하이픈 유무 허용): 010-1234-5678 / 01012345678 등
PHONE_PATTERN = r"^01[016789]-?\d{3,4}-?\d{4}$"

class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    CLIENT = "CLIENT"


class UserState(int, Enum):
    INACTIVE = 0
    ACTIVE = 1

class UserBase(BaseModel):
    """
    사용자 기본 정보 스키마
    """
    name: str = Field(..., description="이름")
    nickname: Optional[str] = Field(None, description="별명")
    email: EmailStr = Field(..., description="이메일")
    phone: Optional[str] = Field(None, description="핸드폰번호")
    emailConf: str = Field("2", description="메일 주소 확인 여부 1: yes 2: no")
    desc: Optional[str] = Field(None, description="설명")
    filePath: Optional[str] = Field(None, description="프로필 파일 아이디")
    extra: Dict[str, Any] = Field(default_factory=dict, description="부가정보")

    # 간편 로그인(Social Login) 확장을 위한 필드
    provider: str = Field("email", description="가입 경로 (email, google, naver, kakao 등)")
    providerId: Optional[str] = Field(None, description="소셜 로그인 제공자 측의 식별자")


class UserCreate(UserBase):
    """
    회원가입 요청 스키마
    - 입력값 규칙(2026-08-25 팀 정책): 닉네임 2~10자·중복 불가, 비밀번호 8자 이상,
      전화번호는 한국 휴대폰 형식. 규칙 위반은 422로 거절된다.
    """
    name: str = Field(..., min_length=1, max_length=100, description="이름")
    nickname: Optional[str] = Field(None, min_length=2, max_length=10, description="별명 (2~10자, 중복 불가)")
    phone: Optional[str] = Field(None, pattern=PHONE_PATTERN, description="핸드폰번호 (01X-XXXX-XXXX, 하이픈 생략 가능)")
    password: Optional[str] = Field(None, min_length=8, description="비밀번호 (8자 이상; 이메일 가입 시 필수, 소셜 로그인 시 선택)")
    passwordCheck: Optional[str] = Field(None, description="비밀번호 확인")
    agreeTerms: bool = Field(True, description="약관 동의 여부")

    @field_validator("nickname", "phone", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        # 클라이언트가 빈 문자열을 보내는 경우 "미입력"으로 취급 (길이/형식 검증 오류 방지)
        if isinstance(v, str) and not v.strip():
            return None
        return v


class UserUpdate(BaseModel):
    """
    회원정보 수정 요청 스키마
    - 변경할 필드만 전달
    """
    name: Optional[str] = None
    nickname: Optional[str] = None
    phone: Optional[str] = None
    desc: Optional[str] = None
    filePath: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class KakaoLogin(BaseModel):
    """
    카카오 로그인 요청 스키마
    - accessToken: 카카오 SDK 로그인으로 클라이언트(iOS)가 발급받은 카카오 액세스 토큰
    """
    accessToken: str = Field(..., description="카카오 액세스 토큰")


class UserLogin(BaseModel):
    """
    이메일 로그인 요청 스키마
    """
    email: EmailStr
    password: str


class SocialLoginRequest(BaseModel):
    """
    소셜 로그인 요청 스키마 (예시)
    """
    provider: str
    token: str  # 클라이언트에서 받은 액세스 토큰 등


class UserResponse(UserBase):
    """
    회원정보 응답 스키마
    """
    id: int
    role: UserRole = Field(UserRole.CLIENT, description="권한 레벨 (SUPER_ADMIN, ADMIN, CLIENT)")
    state: UserState = Field(UserState.ACTIVE, description="계정 상태 (0: INACTIVE, 1: ACTIVE)")
    # password는 제외됨

    class Config:
        from_attributes = True


class Token(BaseModel):
    accessToken: str
    tokenType: str


class TokenData(BaseModel):
    email: Optional[str] = None


class UserExistsRequest(BaseModel):
    """
    사용자 ID 존재 여부 체크 요청 스키마
    """
    id: int


class CheckEmailRequest(BaseModel):
    """
    이메일 중복 체크 요청 스키마
    """
    email: EmailStr


class UserUpdateRequest(BaseModel):
    """
    내 정보 수정 요청 스키마 (변경할 필드만 전달)
    - 가입과 동일한 입력값 규칙 적용 (닉네임 2~10자, 새 비밀번호 8자 이상, 전화번호 형식)
    """
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    nickname: Optional[str] = Field(None, min_length=2, max_length=10)
    phone: Optional[str] = Field(None, pattern=PHONE_PATTERN)
    desc: Optional[str] = None
    filePath: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
    password: Optional[str] = None
    passwordNew: Optional[str] = Field(None, min_length=8)
    passwordNewCheck: Optional[str] = None
