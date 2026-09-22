"""ASGI entry point. No automatic production schema creation or sample seed."""
from __future__ import annotations
import logging, re, time, uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker
from . import installation  # register immutable installation provenance
from .config import Settings
from .core import make_engine
from .models import Audit, utcnow
from .readiness import collect_readiness
from .maintenance_guard import configured_maintenance
from .access_logging import record_access_best_effort
from . import __version__
from .routes import auth, sso, admin, business, calculations, files, tasks, integrations, reference, delivery

log = logging.getLogger("nondegree")

class BodyLimitMiddleware:
    """Bound actual incoming bytes, including chunked uploads, before multipart parsing."""
    def __init__(self, app, limit): self.app, self.limit = app, limit
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        chunks=[]; size=0
        while True:
            message=await receive()
            if message["type"] == "http.disconnect": return
            body=message.get("body",b"");size+=len(body)
            if size>self.limit:
                return await JSONResponse({"detail":"请求过大，附件上限为配置的单文件大小"},413)(scope,receive,send)
            chunks.append(body)
            if not message.get("more_body",False):break
        body=b"".join(chunks);sent=False
        async def replay():
            nonlocal sent
            if not sent:sent=True;return {"type":"http.request","body":body,"more_body":False}
            return await receive()
        await self.app(scope,replay,send)

def create_app(settings: Settings | None = None):
    cfg = settings or Settings()
    if cfg.env == "production":
        from .releasecheck import check_source_release
        check_source_release()
    integrations.ADAPTERS.configure(cfg.env == 'production', [x.strip() for x in cfg.adapter_modules.split(',') if x.strip()])
    engine = make_engine(cfg.database_url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    @asynccontextmanager
    async def lifespan(app):
        if cfg.env == "production":
            with engine.connect() as connection:
                installation.require_canonical(connection, require_mysql=True)
        cfg.storage_dir.mkdir(parents=True,exist_ok=True)
        yield
        engine.dispose()
    app=FastAPI(title="一站式非学历教育智慧前台",version=__version__,lifespan=lifespan,
                docs_url="/api/docs" if cfg.env=="test" else None,redoc_url=None,openapi_url=None)
    app.state.settings,app.state.engine,app.state.sessions=cfg,engine,sessions
    app.add_middleware(BodyLimitMiddleware,limit=(cfg.upload_limit_mb+1)*1024*1024)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=[x.strip() for x in cfg.allowed_hosts.split(",")])

    @app.middleware("http")
    async def security(request:Request,call_next):
        # A server-generated correlation ID prevents log pollution and spoofing.
        request.state.request_id=str(uuid.uuid4());started=time.monotonic()
        maintenance = configured_maintenance(cfg)
        if request.url.path.startswith('/api') and request.url.path != '/api/health' and maintenance['blocked']:
            response = JSONResponse({'code':'MAINTENANCE','detail':'系统维护中，暂不受理业务请求','request_id':request.state.request_id},503,headers={'Retry-After':'60'})
        else:
            response=await call_next(request)
        response.headers["X-Request-ID"]=request.state.request_id
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Referrer-Policy"]="same-origin"
        response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if cfg.secure_cookie:response.headers["Strict-Transport-Security"]="max-age=31536000"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"]="no-store"
            # No query string, body, cookies or authorization secrets in access audit.
            if request.url.path not in {"/api/health"}:
                event = dict(actor_id=getattr(request.state,'actor_id',None),
                    actor_name=getattr(request.state,'actor_name','未登录'),org_id=getattr(request.state,'org_id',None),
                    module='access',object_id=request.url.path[:128],action=request.method,
                    before={},after={'http_status':response.status_code,'elapsed_ms':round((time.monotonic()-started)*1000,1)},
                    reason='服务端访问记录',result='DENIED' if response.status_code in {401,403,404} else 'ERROR' if response.status_code>=400 else 'SUCCESS',request_id=request.state.request_id)
                # Query access logging is explicitly best-effort and must not
                # extend user-visible response time.  Starlette executes this
                # after the response has been sent; critical business audit
                # records remain synchronous in the command transaction.
                task=BackgroundTask(record_access_best_effort,sessions,log,event)
                if response.background is None:
                    response.background=task
                elif isinstance(response.background,BackgroundTasks):
                    response.background.tasks.append(task)
                else:
                    response.background=BackgroundTasks([response.background,task])
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request,exc):
        return JSONResponse({"detail":exc.detail,"request_id":getattr(request.state,"request_id","")},exc.status_code,headers=exc.headers)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        errors=[{"field":".".join(str(x) for x in e["loc"]),"message":e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail":"输入校验未通过","errors":errors,"request_id":getattr(request.state,"request_id","")},422)
    @app.exception_handler(IntegrityError)
    async def integrity_error(request,exc):
        log.warning("Integrity conflict request=%s",getattr(request.state,"request_id",""))
        return JSONResponse({"detail":"数据重复或关联关系冲突；本次事务已回滚，请刷新核对","request_id":getattr(request.state,"request_id","")},409)
    @app.exception_handler(OperationalError)
    async def database_error(request,exc):
        log.error("Database error request=%s type=%s",getattr(request.state,"request_id",""),type(exc).__name__)
        return JSONResponse({"detail":"数据库暂不可用或结果尚未确认，请先核对业务结果；不要直接重复提交","request_id":getattr(request.state,"request_id","")},503)
    @app.exception_handler(Exception)
    async def unexpected(request,exc):
        log.error("Unhandled error request=%s type=%s",getattr(request.state,"request_id",""),type(exc).__name__)
        return JSONResponse({"detail":"请求未完成，请凭请求编号联系管理员","request_id":getattr(request.state,"request_id","")},500)

    @app.get("/api/health")
    def health():
        report = collect_readiness(engine,cfg,__version__)
        return JSONResponse(report,200 if report['status']=='ok' else 503)
    for router in (auth.router,sso.router,admin.router,business.router,calculations.router,files.router,tasks.router,integrations.router,reference.router,delivery.router):app.include_router(router)
    # A local review server only. Production frontend is served by the separate nginx service.
    if cfg.env=="test":
        frontend=Path(__file__).resolve().parents[2]/"frontend"
        if not frontend.exists():frontend=Path(__file__).resolve().parents[3]/"frontend"
        if frontend.exists():
            @app.get("/")
            def index():return FileResponse(frontend/"index.html")
            app.mount("/assets",StaticFiles(directory=frontend),name="assets")
    return app
