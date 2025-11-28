from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .routers import cctv, food, gym, health, media, tasks
from .services.gym_seed import seed_gym_defaults

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(tasks.router, prefix=settings.api_prefix)
app.include_router(food.router, prefix=settings.api_prefix)
app.include_router(gym.router, prefix=settings.api_prefix)
app.include_router(cctv.router, prefix=settings.api_prefix)
app.include_router(media.router, prefix=settings.api_prefix)


@app.on_event("startup")
def _prime_seed_data() -> None:
    seed_gym_defaults()
