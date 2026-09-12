from fastapi import FastAPI

app = FastAPI(title="Nokware Backend", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Routers are registered here as they are added under app/routes/.
