from fastapi import FastAPI

from app.routes import ask
from app.services.appwrite_client import quiet_sdk_deprecation_warnings

quiet_sdk_deprecation_warnings()

app = FastAPI(title="Nokware Backend", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ask.router)
