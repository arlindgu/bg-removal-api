from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import require_api_key, require_master_key
from app.config import settings
from app.db import ApiKey, add_credits, consume_credit, create_api_key, get_api_key_by_key, get_session, init_db
from app.inference import fetch_image_from_url, get_model_session, remove_background


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    get_model_session()  # warm up the model so the first request isn't slow
    yield


app = FastAPI(title="Background Removal API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/credits")
def credits(api_key: ApiKey = Depends(require_api_key)):
    return {"credits": api_key.credits}


@app.post("/v1/remove-background")
async def remove_background_endpoint(
    file: UploadFile | None = File(None),
    image_url: str | None = Form(None),
    api_key: ApiKey = Depends(require_api_key),
):
    if bool(file) == bool(image_url):
        raise HTTPException(400, "Provide exactly one of: file, image_url")

    if file:
        image_bytes = await file.read()
        max_bytes = settings.max_image_mb * 1024 * 1024
        if len(image_bytes) > max_bytes:
            raise HTTPException(400, f"Image exceeds {settings.max_image_mb}MB limit")
    else:
        try:
            image_bytes = await fetch_image_from_url(image_url)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    with get_session() as session:
        if not consume_credit(session, api_key):
            raise HTTPException(402, "Insufficient credits")

    try:
        result = await remove_background(image_bytes)
    except Exception as exc:
        with get_session() as session:
            add_credits(session, api_key, 1, "refund: processing failed")
        raise HTTPException(500, f"Processing failed: {exc}")

    return Response(content=result, media_type="image/png")


# --- Admin endpoints, protected by the master key, used to issue keys and grant credits ---


class CreateKeyRequest(BaseModel):
    name: str
    initial_credits: int = 0


class GrantCreditsRequest(BaseModel):
    amount: int
    reason: str


@app.post("/admin/keys", dependencies=[Depends(require_master_key)])
def admin_create_key(body: CreateKeyRequest):
    with get_session() as session:
        api_key = create_api_key(session, body.name, body.initial_credits)
        return {"key": api_key.key, "name": api_key.name, "credits": api_key.credits}


@app.get("/admin/keys/{key}", dependencies=[Depends(require_master_key)])
def admin_get_key(key: str):
    with get_session() as session:
        api_key = get_api_key_by_key(session, key)
        if not api_key:
            raise HTTPException(404, "Key not found")
        return {"name": api_key.name, "credits": api_key.credits, "active": api_key.active}


@app.post("/admin/keys/{key}/credits", dependencies=[Depends(require_master_key)])
def admin_grant_credits(key: str, body: GrantCreditsRequest):
    with get_session() as session:
        api_key = get_api_key_by_key(session, key)
        if not api_key:
            raise HTTPException(404, "Key not found")
        api_key = add_credits(session, api_key, body.amount, body.reason)
        return {"name": api_key.name, "credits": api_key.credits}
