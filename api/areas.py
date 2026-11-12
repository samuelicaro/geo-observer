import json
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from api.database import session
from api.schemas import AreaCriacao, AreaLeitura
from models.models import AreaInteresse, Imagem

router = APIRouter(prefix='/areas', tags=['Áreas de interesse'])

def serializar(item, db):
    geometry = db.scalar(select(func.ST_AsGeoJSON(item.geometria, 15)))
    return AreaLeitura(id=item.id, nome=item.nome, imagem_id=item.imagem_id,
                       geometria=json.loads(geometry), criado_em=item.criado_em)

def validar(body, db):
    geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(body.geometria.model_dump_json()), 4326)
    if not db.scalar(select(func.ST_IsValid(geom))) or db.scalar(select(func.ST_Area(geom))) <= 0:
        raise HTTPException(422, 'Polígono inválido: verifique cruzamentos e área nula.')
    if body.imagem_id is not None:
        image = db.get(Imagem, body.imagem_id)
        if image is None:
            raise HTTPException(404, 'Imagem não encontrada.')
        if image.area_coberta is None:
            raise HTTPException(422, 'Imagem sem extensão geográfica cadastrada.')
        if not db.scalar(select(func.ST_Covers(image.area_coberta, geom))):
            raise HTTPException(422, 'A área deve estar dentro da extensão geográfica da imagem.')
    return geom

@router.get('/', response_model=list[AreaLeitura])
def listar(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(session)):
    return [serializar(item, db) for item in db.scalars(select(AreaInteresse).order_by(AreaInteresse.criado_em, AreaInteresse.id).limit(limit).offset(offset))]

@router.post('/', response_model=AreaLeitura, status_code=201)
def criar(body: AreaCriacao, db: Session = Depends(session)):
    existing = db.get(AreaInteresse, str(body.id))
    if existing is not None:
        result = serializar(existing, db)
        if result.nome == body.nome and result.imagem_id == body.imagem_id and db.scalar(select(func.ST_Equals(existing.geometria, func.ST_SetSRID(func.ST_GeomFromGeoJSON(body.geometria.model_dump_json()), 4326)))):
            return result
        raise HTTPException(409, 'ID já cadastrado com outros dados. Atualize a área existente.')
    geom = validar(body, db)
    item = AreaInteresse(id=str(body.id), nome=body.nome, imagem_id=body.imagem_id, geometria=geom)
    db.add(item)
    return gravar(item, db)

def gravar(item, db):
    try:
        db.flush()
        result = serializar(item, db)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Conflito ao salvar. Atualize a lista e confira a imagem vinculada.') from exc

@router.put('/{area_id}', response_model=AreaLeitura)
def atualizar(area_id: str, body: AreaCriacao, db: Session = Depends(session)):
    item = db.get(AreaInteresse, area_id)
    if item is None:
        raise HTTPException(404, 'Área não encontrada.')
    if str(body.id) != area_id:
        raise HTTPException(422, 'O ID do corpo deve ser igual ao da rota.')
    geom = validar(body, db)
    item.nome, item.imagem_id, item.geometria = body.nome, body.imagem_id, geom
    return gravar(item, db)

@router.delete('/{area_id}', status_code=204)
def remover(area_id: str, db: Session = Depends(session)):
    item = db.get(AreaInteresse, area_id)
    if item is None:
        raise HTTPException(404, 'Área não encontrada.')
    db.delete(item)
    db.commit()
    return Response(status_code=204)
