import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from minio.error import S3Error
from urllib3.exceptions import HTTPError
from api import imagens, processamentos, usuarios

app = FastAPI(title="Geo Observer")
static = Path(__file__).resolve().parents[1] / "static"
app.mount("/static", StaticFiles(directory=static), name="static")
templates = Jinja2Templates(directory=static)
app.include_router(imagens.router)
app.include_router(processamentos.router)
app.include_router(usuarios.router)

async def unavailable(request, exc):
    logging.getLogger(__name__).error("Falha de infraestrutura", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Serviço indisponível; confira configuração e infraestrutura."})

for error in (SQLAlchemyError, S3Error, HTTPError, RuntimeError, KeyError):
    app.add_exception_handler(error, unavailable)

@app.get("/health")
def health():
    return {"status": "ok", "tipo": "liveness"}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

