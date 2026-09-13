from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import ask, me
from app.services.appwrite_client import quiet_sdk_deprecation_warnings

quiet_sdk_deprecation_warnings()
settings = get_settings()

app = FastAPI(title="Nokware Backend", version="0.1.0")

# Auth travels in the Authorization header, never in cookies, so credentials
# stay off and only the headers the frontend sends are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ask.router)
app.include_router(me.router)
