from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config import get_settings
from .routers import auth, watchlist, market, notes

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting {settings.app_name}")
    yield
    # Shutdown
    print("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="Global stock market research and watchlist platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(watchlist.router)
app.include_router(market.router)
app.include_router(notes.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
