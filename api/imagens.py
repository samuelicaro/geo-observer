import json
import logging
import os
from pathlib import Path
from tempfile import SpooledTemporaryFile
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from api.acesso import session
from api.storage import storage, bucket
from models.models import Imagem, Processamento, OrigemImagem
from api.schemas import ImagemLeitura, ImagemRenomear
from fastapi.responses import Response
from api.previas import gerar_previa
from api.raster import metadados

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

@router.patch("/{imagem_id}", response_model=ImagemLeitura)
def renomear(imagem_id: int, body: ImagemRenomear, db: Session = Depends(session)):
    item = db.get(Imagem, imagem_id)
    if item is None:
        raise HTTPException(404, "Imagem não encontrada")
    item.nome_original = body.nome_original
    db.commit()
    return serialize(item)

@router.delete("/{imagem_id}", response_model=ImagemLeitura)
def remover(imagem_id: int, db: Session = Depends(session)):
    item = db.get(Imagem, imagem_id)
    if item is None:
        raise HTTPException(404, "Imagem não encontrada")

    vinculo = db.scalar(
        select(Processamento.id).where(Processamento.imagem_id == imagem_id).limit(1)
    )
    if vinculo is not None:
        raise HTTPException(409, "A imagem possui processamentos vinculados e não pode ser removida.")

    resposta = ImagemLeitura.model_validate(item)
    target, key = item.bucket, item.objeto_chave
    try:
        db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Também cobre um processamento criado entre a consulta e a exclusão.
        if getattr(exc.orig, "sqlstate", None) in {"23001", "23502", "23503"}:
            raise HTTPException(409, "A imagem está vinculada a uma área ou análise e não pode ser excluída.") from None
        raise
    try:
        storage().remove_object(target, key)
    except Exception:
        # A linha já foi excluída; registrar o objeto órfão para limpeza operacional.
        logger.exception("Objeto MinIO órfão após excluir imagem %s: %s/%s", imagem_id, target, key)
    return resposta

def persistir(file, nome, size, db, origem=None):
    dados = metadados(file)
    file.seek(0)
    client, target, key = storage(), bucket(), f"originais/{uuid4()}.tif"
    client.put_object(target, key, file, size, content_type="image/tiff")
    item = Imagem(nome_original=nome, bucket=target, objeto_chave=key, tamanho_bytes=size, **dados)
    try:
        db.add(item)
        db.flush()
        if origem is not None:
            db.add(OrigemImagem(imagem_id=item.id, dados=origem))
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


@router.get('/{imagem_id}/origem')
def origem(imagem_id: int, db: Session = Depends(session)):
    if db.get(Imagem, imagem_id) is None:
        raise HTTPException(404, 'Imagem não encontrada')
    row = db.get(OrigemImagem, imagem_id)
    return row.dados if row else {'provedor': 'upload local ou registro anterior'}


@router.get('/{imagem_id}/extensao')
def extensao(imagem_id: int, db: Session = Depends(session)):
    item = db.get(Imagem, imagem_id)
    if item is None:
        raise HTTPException(404, 'Imagem não encontrada')
    if item.area_coberta is None:
        raise HTTPException(422, 'Imagem sem extensão geográfica cadastrada.')
    geometry = json.loads(db.scalar(select(func.ST_AsGeoJSON(item.area_coberta, 15))))
    return {'type': 'Feature', 'properties': {'imagem_id': item.id,
            'nome': item.nome_original, 'tipo': 'extensao_cadastrada'}, 'geometry': geometry}


@router.get('/{imagem_id}/previa-mapa')
def previa_mapa(imagem_id: int, db: Session = Depends(session)):
    import base64
    item = db.get(Imagem, imagem_id)
    if item is None:
        raise HTTPException(404, 'Imagem não encontrada')
    png, bounds = gerar_previa(item, mapa=True)
    return {'imagem_id':item.id, 'bounds':bounds,
            'imagem_url':'data:image/png;base64,'+base64.b64encode(png).decode('ascii')}
