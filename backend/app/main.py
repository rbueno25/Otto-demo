import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import run_agent
from .config import load_settings
from .odoo_client import OdooClient, OdooError

settings = load_settings()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Otto - Asistente de Odoo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    messages: list[dict]


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not settings.is_odoo_configured():
        raise HTTPException(
            status_code=503,
            detail="Odoo no está configurado. Completa ODOO_URL, ODOO_DB, ODOO_USER y ODOO_PASSWORD en el .env",
        )
    if not settings.ai_api_endpoint or not settings.ai_api_key:
        raise HTTPException(status_code=503, detail="La IA no está configurada. Revisa AI_API_* en el .env")

    async def gen():
        odoo = OdooClient(settings)
        try:
            await odoo.authenticate()
        except OdooError as exc:
            yield sse({"type": "error", "message": str(exc)})
            yield sse({"type": "done"})
            await odoo.aclose()
            return
        try:
            async for event in run_agent(odoo, settings, req.messages):
                yield sse(event)
        finally:
            await odoo.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    odoo_ok = None
    odoo_detail = None
    if settings.is_odoo_configured():
        odoo = OdooClient(settings)
        try:
            uid = await odoo.authenticate()
            user = await odoo.read("res.users", [uid], ["name"])
            odoo_ok = True
            odoo_detail = {"uid": uid, "usuario": user[0]["name"] if user else "?"}
        except OdooError as exc:
            odoo_ok = False
            odoo_detail = str(exc)
        finally:
            await odoo.aclose()
    return {
        "odoo": {
            "configurado": settings.is_odoo_configured(),
            "url": settings.odoo_url,
            "ok": odoo_ok,
            "detalle": odoo_detail,
        },
        "ia": {
            "configurado": bool(settings.ai_api_endpoint and settings.ai_api_key),
            "endpoint": settings.ai_api_endpoint,
            "modelo": settings.ai_model,
        },
    }


# --- Frontend estático --- #

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
