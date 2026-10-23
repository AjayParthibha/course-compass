import threading
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalog.store import get_catalog
from app.config import get_settings
from app.routes import auth, chat, explore, onboarding, plans, profile

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # load the catalog now rather than on the first request that needs it (about a second)
    threading.Thread(target=get_catalog, daemon=True).start()
    yield


app = FastAPI(title="CourseCompass", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
for module in (auth, plans, profile, onboarding, explore, chat):
    api.include_router(module.router)


@api.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(api)

# In production the built frontend is served from the same container.
if (settings.static_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=settings.static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        root = settings.static_dir.resolve()
        file = (root / path).resolve()
        if file.is_file() and file.is_relative_to(root):
            return FileResponse(file)
        return FileResponse(root / "index.html")
