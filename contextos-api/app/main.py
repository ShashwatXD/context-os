"""ContextOS API Application Entrypoint."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.exceptions import ContextOSError, EntityNotFoundError, PermissionDeniedError, ApprovalRequiredError
from app.infrastructure.database.session import close_db, init_db
from app.interfaces.api.routes import (
    agents,
    approvals,
    assets,
    context,
    evaluations,
    graph,
    health,
    sources,
    traces,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database schema tables on startup and cleans up on shutdown."""
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "EntityNotFound", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "PermissionDenied", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(ApprovalRequiredError)
async def approval_required_handler(request: Request, exc: ApprovalRequiredError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "ApprovalRequired", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(ContextOSError)
async def domain_error_handler(request: Request, exc: ContextOSError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "DomainError", "message": exc.message, "details": exc.details},
    )


# Mount API v1 Routes
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(sources.router, prefix=settings.API_V1_PREFIX)
app.include_router(assets.router, prefix=settings.API_V1_PREFIX)
app.include_router(graph.router, prefix=settings.API_V1_PREFIX)
app.include_router(context.router, prefix=settings.API_V1_PREFIX)
app.include_router(agents.router, prefix=settings.API_V1_PREFIX)
app.include_router(approvals.router, prefix=settings.API_V1_PREFIX)
app.include_router(traces.router, prefix=settings.API_V1_PREFIX)
app.include_router(evaluations.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX,
    }

