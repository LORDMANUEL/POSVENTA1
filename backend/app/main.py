from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from .accounting_api import accounting_router
from .admin_api import admin_router, device_router
from .analytics_api import analytics_router
from .api import router
from .automation_api import integration_router, workflow_router
from .bank_reconciliation_api import reconciliation_router
from .catalog_import_api import catalog_import_router
from .catalog_media_import_api import router as catalog_media_import_router
from .commerce_api import commerce_router, store_router
from .config import get_settings
from .content_api import ads_router, cms_router, marketing_router
from .crm_api import crm_router, loyalty_router, notification_router
from .db import Base, engine
from .experience_api import music_router, visual_router
from .finance_api import banking_router, payables_router, receivables_router
from .fiscal_api import fiscal_router
from .inventory_advanced_api import inventory_advanced_router
from .knowledge_api import ai_router, rag_router
from .media_api import media_router
from .module_api import module_router, require_enabled_module
from .ops_api import ops_router
from .people_api import attendance_router, hr_router, payroll_router
from .post_sale_api import post_sale_router

APP_VERSION = "0.12.1"
settings = get_settings()
media_path = Path(settings.media_root)
media_path.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Mily Zebra Commerce OS API",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=str(media_path)), name="media")


@app.exception_handler(StaleDataError)
async def stale_data_conflict(_: Request, __: StaleDataError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": (
                "La operación cambió mientras se procesaba. "
                "Recargue el estado actual y vuelva a intentarlo."
            )
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_conflict(_: Request, __: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "La operación entró en conflicto con el estado actual"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "mily-zebra-api",
        "version": APP_VERSION,
    }


app.include_router(router)
app.include_router(ops_router)
app.include_router(inventory_advanced_router)
app.include_router(media_router)
app.include_router(catalog_import_router)
app.include_router(catalog_media_import_router)
app.include_router(admin_router)
app.include_router(device_router)
app.include_router(module_router)
app.include_router(post_sale_router)
app.include_router(store_router)
app.include_router(commerce_router)
app.include_router(
    accounting_router,
    dependencies=[Depends(require_enabled_module("accounting"))],
)
app.include_router(receivables_router)
app.include_router(payables_router)
app.include_router(banking_router)
app.include_router(reconciliation_router)
app.include_router(fiscal_router)
app.include_router(crm_router)
app.include_router(loyalty_router)
app.include_router(notification_router)
app.include_router(hr_router)
app.include_router(attendance_router)
app.include_router(payroll_router)
app.include_router(cms_router)
app.include_router(marketing_router)
app.include_router(ads_router)
app.include_router(workflow_router)
app.include_router(integration_router)
app.include_router(music_router)
app.include_router(visual_router)
app.include_router(rag_router)
app.include_router(ai_router)
app.include_router(analytics_router)
