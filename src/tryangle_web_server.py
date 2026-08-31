"""
 Copyright (c) 2025. Ebee1205(wavicle) all rights reserved.

 The copyright of this software belongs to Ebee1205(wavicle).
 All rights reserved.
"""

# main.py
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import traceback
import asyncio
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.app_context import AppContext
from src.core.responses import build_error_response

from src.service.basic.basic_api import router as basic_router
from src.service.reference.reference_api import router as reference_router
from src.service.files.files_api import router as files_router
from src.service.auth.auth_api import router as auth_router
from src.service.ctg.ctg_api import router as ctg_router
from src.service.prod.prod_api import router as prod_router
from src.service.session.session_api import router as session_router
from src.service.snap.snap_api import router as snap_router
from src.service.system.system_api import router as system_router

class AppFactory:
    """애플리케이션 팩토리 클래스"""
    
    @staticmethod
    def create_app() -> FastAPI:
        """FastAPI 애플리케이션 생성 및 설정"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            ctx = None
            try:
                ctx = app.state.ctx
                await AppFactory._startup(app)
                yield
            except asyncio.CancelledError:
                if ctx and hasattr(ctx, 'log'):
                    ctx.log.warning("     - Application interrupted by user (CancelledError)")
                else:
                    print("     Application interrupted by user (CancelledError)")
                raise  # shutdown 호출을 위해 재전파 필요
            except Exception as e:
                if ctx and hasattr(ctx, 'log'):
                    ctx.log.error(f"     - Unexpected error during startup: {e}")
                else:
                    print(f"     Unexpected error during startup: {e}")
                traceback.print_exc()
                raise
            finally:
                if ctx and hasattr(ctx, 'log'):
                    ctx.log.info("     - Starting graceful shutdown")
                else:
                    print("     Starting graceful shutdown")
                await AppFactory._shutdown(app)

        
        app = FastAPI(lifespan=lifespan)
        
        # 컨텍스트 초기화
        ctx = AppContext()
        app.state.ctx = ctx
        
        # 설정 로드
        ctx.load_config("src/service/conf/tryangle_web_server.local.cfg.json")

        # 처리되지 않은 예외 → JSON 500 변환.
        # CORS 미들웨어보다 먼저(=안쪽에) 등록해야 오류 응답에도 CORS 헤더가 붙는다.
        # (없으면 예외가 헤더 없는 text 500으로 나가서 브라우저에서 CORS 오류로 둔갑)
        @app.middleware("http")
        async def unhandled_exception_to_json(request, call_next):
            try:
                return await call_next(request)
            except Exception:
                if ctx.log:
                    ctx.log.error("Unhandled exception", exc_info=True)
                else:
                    traceback.print_exc()
                return JSONResponse(status_code=500, content=build_error_response(500))

        # CORS 설정
        AppFactory._setup_cors(app, ctx)
        
        # 라우터 등록
        AppFactory._register_routes(app)
        
        return app
    
    @staticmethod
    def _setup_cors(app: FastAPI, ctx: AppContext) -> None:
        """CORS 미들웨어 설정"""
        cors_config = ctx.cfg.http_config
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_config.allow_origins,
            allow_credentials=cors_config.allow_credentials,
            allow_methods=cors_config.allow_methods,
            allow_headers=cors_config.allow_headers,
        )
        print(f"CORS configuration complete: {cors_config.allow_origins}")

    @staticmethod
    def _register_routes(app: FastAPI) -> None:
        """라우터 등록"""
        routers = [
            basic_router,
            reference_router,
            files_router,
            auth_router,
            ctg_router,
            prod_router,
            session_router,
            snap_router,
            system_router,
        ]
        for router in routers:
            app.include_router(router)
    
    @staticmethod
    async def _startup(app: FastAPI) -> None:
        """애플리케이션 시작 시 초기화"""
        try:
            print("     - Initializing application...")
            ctx = app.state.ctx

            # 초기화 후 연결 설정
            await AppFactory._initialize_managers(ctx)
            await AppFactory._initialize_handlers(ctx)
            
            ctx.log.info("     == Initialization complete")

        except Exception as e:
            if hasattr(app.state, 'ctx') and hasattr(app.state.ctx, 'log'):
                app.state.ctx.log.error(f"     -- Initialization error: {str(e)}")
            else:
                print(f"     -- Initialization error: {str(e)}")
            traceback.print_exc()
            raise
        
    @staticmethod
    async def _initialize_managers(ctx: AppContext) -> None:
        """매니저 초기화"""
        print("     - Initializing managers...")
        ctx._init_logger()

    @staticmethod
    async def _initialize_handlers(ctx: AppContext) -> None:
        """핸들러 초기화"""    
        ctx.log.info("     - Initializing handlers...")
        ctx._init_db()
        AppFactory._verify_schema(ctx)

    @staticmethod
    def _verify_schema(ctx: AppContext) -> None:
        """마이그레이션 미적용을 조용한 500 폭탄 대신 기동 로그에서 드러낸다.

        _AGG_COLS가 세션 4개 엔드포인트를 tb_rt_snapshot에 의존시키므로,
        테이블이 없으면 세션 기능 전체가 죽는다 — 헬스체크로는 탐지 불가.
        (마이그레이션은 레포 정책상 수동 적용: src/sql/migrations/)
        """
        try:
            from src.utils.db_utils import execute_query
            execute_query(ctx.db_handler, "SELECT 1 FROM tb_rt_snapshot LIMIT 1")
        except Exception as e:
            ctx.log.critical(
                "     !! tb_rt_snapshot 확인 실패 — src/sql/migrations/2026-08-31_rt_snapshot.sql "
                f"미적용 시 세션 API(start/end/list/detail) 전체가 500이 됩니다: {e}"
            ) 

    
    @staticmethod
    async def _shutdown(app: FastAPI) -> None:
        """애플리케이션 종료 시 정리"""
        ctx = app.state.ctx

        if hasattr(ctx, 'log') and ctx.log:
            ctx.log.info("     -- Shutting down application")

# 애플리케이션 인스턴스 생성
app = AppFactory.create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.tryangle_web_server:app", host="0.0.0.0", port=8738, reload=True)