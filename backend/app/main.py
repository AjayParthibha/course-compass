from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import auth, explore, onboarding, plans, profile

settings = get_settings()
app = FastAPI(title="CourseCompass")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
for module in (auth, plans, profile, onboarding, explore):
    api.include_router(module.router)


@api.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(api)
