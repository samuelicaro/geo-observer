import logging
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from minio.error import S3Error
from urllib3.exceptions import HTTPError
from api import imagens, processamentos, usuarios, earth_engine, areas, auth, google_login

app = FastAPI(title="Geo Observer", root_path=os.environ.get("API_ROOT_PATH", ""))
app.include_router(imagens.router)
app.include_router(processamentos.router)
app.include_router(usuarios.router)
app.include_router(earth_engine.router)
app.include_router(areas.router)
app.include_router(auth.router)
app.include_router(google_login.router)

async def unavailable(request, exc):
    logging.getLogger(__name__).error("Falha de infraestrutura", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Serviço indisponível; confira configuração e infraestrutura."})

for error in (SQLAlchemyError, S3Error, HTTPError, RuntimeError, KeyError):
    app.add_exception_handler(error, unavailable)

@app.get("/health")
def health():
    return {"status": "ok", "tipo": "liveness"}

@app.get('/')
def index():
    return {'servico':'Geo Observer API','documentacao':'/docs'}

@app.middleware('http')
async def proteger_requisicao(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('X-Geo-Request') != '1':
            return JSONResponse(status_code=403, content={'detail':'Envie o cabeçalho X-Geo-Request: 1.'})
    response = await call_next(request)
    if not request.url.path.startswith('/static/'):
        response.headers['Cache-Control']='no-store'
    return response


@app.get('/ready')
def ready():
    from sqlalchemy import text
    from api.database import engine
    from api.storage import storage,bucket
    from worker.broker import conectar
    with engine().connect() as db:db.execute(text('SELECT 1'))
    if not storage().bucket_exists(bucket()):
        return JSONResponse(status_code=503,content={'status':'indisponivel'})
    try:
        connection,_=conectar()
        connection.close()
    except Exception:
        return JSONResponse(status_code=503,content={'status':'indisponivel'})
    return {'status':'ok','servicos':['postgis','minio','rabbitmq']}
