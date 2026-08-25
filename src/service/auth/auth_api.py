from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm

from src.core.responses import build_response_body, build_success_response, ResponseStatus
from src.service.auth import auth_service, kakao_service
from src.service.auth.auth_schema import UserCreate, UserLogin, KakaoLogin, UserExistsRequest, CheckEmailRequest, UserUpdateRequest
from src.service.auth.jwt_auth import require_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/signup", status_code=201)
async def signup(request: Request, user: UserCreate):
    """
    회원가입 API
    """
    ctx = request.app.state.ctx
    
    # 비밀번호 확인 체크
    if user.password and user.passwordCheck:
        if user.password != user.passwordCheck:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password match failed"
            )

    newUser = auth_service.create_user(ctx, user)
    return build_response_body(ResponseStatus.CREATED, newUser)


@router.post("/login")
async def login(request: Request, loginReq: UserLogin):
    """
    로그인 API (JSON Body)
    """
    ctx = request.app.state.ctx
    user = auth_service.authenticate_user(ctx, loginReq.email, loginReq.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    accessToken = auth_service.create_access_token(
        ctx,
        data={"sub": user["email"], "role": user["role"]}
    )
    return build_success_response({"accessToken": accessToken, "tokenType": "bearer"})


@router.post("/token")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 폼 로그인 — Swagger UI의 Authorize 버튼과 폼 기반 클라이언트용 (username 칸에 이메일)
    응답 키는 OAuth2 표준(access_token/token_type) 형식이어야 Swagger가 토큰을 인식한다.
    """
    ctx = request.app.state.ctx
    user = auth_service.authenticate_user(ctx, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    accessToken = auth_service.create_access_token(
        ctx,
        data={"sub": user["email"], "role": user["role"]}
    )
    return {"access_token": accessToken, "token_type": "bearer"}


@router.post("/kakao")
async def kakao_login(request: Request, body: KakaoLogin):
    """
    카카오 로그인 API (JSON Body)
    - 클라이언트(iOS)가 카카오 SDK로 받은 액세스 토큰을 보내면,
      검증 후 기존 회원 연결 또는 자동 가입하고 자체 JWT를 발급한다.
    - 응답 형식은 /login과 동일 (+ isNewUser: 이번에 자동 가입됐는지)
    """
    ctx = request.app.state.ctx
    user, is_new = await kakao_service.authenticate_kakao_user(ctx, body.accessToken)

    accessToken = auth_service.create_access_token(
        ctx,
        data={"sub": user["email"], "role": user["role"]}
    )
    return build_success_response({"accessToken": accessToken, "tokenType": "bearer", "isNewUser": is_new})


@router.get("/me")
async def readUsersMe(request: Request, user=Depends(require_user)):
    """
    현재 사용자 정보 조회 (JWT 인증) -> DB tb_user.fileId 문자열이 그대로 데이터 레이어의 filePath로 내려갑니다.
    """
    safe_user = dict(user)
    safe_user.pop("password", None)
    return build_success_response(safe_user)


@router.post("/exists")
async def checkExists(request: Request, body: UserExistsRequest):
    """
    사용자 ID 존재 여부 체크
    """
    ctx = request.app.state.ctx
    exists = auth_service.check_user_exists(ctx, body.id)
    return build_success_response({"id": body.id, "exists": exists})


@router.post("/checkEmail")
async def checkEmail(request: Request, body: CheckEmailRequest):
    """
    이메일 중복 체크
    """
    ctx = request.app.state.ctx
    exists = auth_service.check_email_exists(ctx, body.email)
    return build_success_response({"email": body.email, "exists": exists})


@router.post("/logout")
async def logout(user=Depends(require_user)):
    """
    로그아웃
    """
    return build_success_response({"message": "Logged out successfully"})


@router.post("/update")
async def updateUser(request: Request, body: UserUpdateRequest, user=Depends(require_user)):
    """
    내 정보 수정 (JWT 인증) -> 스키마 구조(body.fileId)를 유지한 채 서비스에 바인딩
    """
    ctx = request.app.state.ctx
    userId = user["id"]
    
    # 클라이언트가 실제로 전송한 필드만 추출 (여기서 fileId에 파일 경로 문자열이 담겨 있습니다)
    update_data = body.model_dump(exclude_unset=True)
    
    success = auth_service.update_user(ctx, userId, update_data)
    if success:
        return build_success_response({"message": "User updated successfully"})
    else:
        raise HTTPException(status_code=400, detail="User update failed")