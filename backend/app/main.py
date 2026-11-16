from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.api import health
from app.auth.router import router as auth_router
from app.budget.router import router as budget_router
from app.clients.router import router as clients_router
from app.core.config import get_settings
from app.core.context import RequestContextMiddleware
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import dispose_engine
from app.documents.router import router as documents_router
from app.events.router import router as events_router
from app.moodboards.router import router as moodboards_router
from app.notifications.router import router as notifications_router
from app.organizations.router import router as organizations_router
from app.portal.router import router as portal_router
from app.privacy.router import router as privacy_router
from app.projects.router import router as projects_router
from app.tasks.router import router as tasks_router
from app.templates.router import router as templates_router
from app.vendors.router import router as vendors_router

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Wedding Planning Platform API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs" if settings.docs_enabled else None,
        redoc_url=None,
    )
    register_error_handlers(app)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(organizations_router, prefix=API_PREFIX)
    for module_router in (
        clients_router,
        vendors_router,
        templates_router,
        projects_router,
        tasks_router,
        budget_router,
        portal_router,
        documents_router,
        events_router,
        notifications_router,
        privacy_router,
        admin_router,
        moodboards_router,
    ):
        app.include_router(module_router, prefix=API_PREFIX)
    return app


app = create_app()
