from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .accounting_api import accounting_router
from .admin_api import admin_router, device_router
from .api import router
from .commerce_api import commerce_router, store_router
from .config import get_settings
from .db import Base, engine
from .module_api import module_router
from .ops_api import ops_router
from .post_sale_api import post_sale_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Test/development convenience only. Production .env disables this and Alembic owns schema changes.
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Mily Zebra Commerce OS API",
    version="0.6.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mily-zebra-api"}


app.include_router(router)
app.include_router(ops_router)
app.include_router(admin_router)
app.include_router(device_router)
app.include_router(module_router)
app.include_router(post_sale_router)
app.include_router(store_router)
app.include_router(commerce_router)
app.include_router(accounting_router)
