import logging
import os
from pathlib import Path
from tempfile import SpooledTemporaryFile
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session
from api.database import session
from api.storage import storage, bucket
from models.models import Imagem
from api.schemas import ImagemLeitura
from fastapi.responses import Response
from api.previas import gerar_previa

router = APIRouter(prefix="/imagens", tags=["Imagens"])
logger = logging.getLogger(__name__)

def serialize(item):
    return ImagemLeitura.model_validate(item)

@router.get("/", response_model=list[ImagemLeitura])
def listar(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(session)):
    return [serialize(row) for row in db.scalars(select(Imagem).order_by(Imagem.id).limit(limit).offset(offset))]

@router.get("/{imagem_id}", response_model=ImagemLeitura)
def obter(imagem_id: int, db: Session = Depends(session)):
    item = db.get(Imagem, imagem_id)
    if item is None:
        raise HTTPException(404, "Imagem não encontrada")
    return serialize(item)

def persistir(file, nome, size, db):
    client, target, key = storage(), bucket(), f"originais/{uuid4()}.tif"
    client.put_object(target, key, file, size, content_type="image/tiff")
    item = Imagem(nome_original=nome, bucket=target, objeto_chave=key, tamanho_bytes=size)
    try:
        db.add(item)
        db.flush()
        result = serialize(item)
        db.commit()
        return result
    except Exception:
        db.rollback()
        try:
            client.remove_object(target, key)
        except Exception:
            logger.exception("Objeto órfão requer reconciliação: %s/%s", target, key)
        raise

@router.post("/", status_code=201, response_model=ImagemLeitura)
async def enviar(request: Request, nome: str = Query(..., min_length=1, max_length=255), db: Session = Depends(session)):
    # Corpo binário evita carregar um TIFF inteiro na memória.
    nome = Path(nome.replace("\\", "/")).name
    if Path(nome).suffix.lower() not in {".tif", ".tiff"}:
        raise HTTPException(415, "Envie um arquivo .tif ou .tiff")
    maximum = int(os.environ.get("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as file:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > maximum:
                raise HTTPException(413, "Arquivo acima do limite configurado")
            await run_in_threadpool(file.write, chunk)
        file.seek(0)
        if file.read(4) not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
            raise HTTPException(415, "Cabeçalho TIFF inválido")
        file.seek(0)
        return await run_in_threadpool(persistir, file, nome, size, db)

@router.get('/{imagem_id}/previa', response_class=Response, responses={200: {'content': {'image/png': {}}}})
def previa(imagem_id: int, db: Session = Depends(session)):
    item = db.get(Imagem, imagem_id)
    if item is None:
        raise HTTPException(404, 'Imagem não encontrada')
    return Response(gerar_previa(item), media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})

