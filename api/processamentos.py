from fastapi import APIRouter, Depends, HTTPException, Query
from api.schemas import ProcessamentoCriacao, ProcessamentoLeitura
from sqlalchemy import select
from sqlalchemy.orm import Session
from api.database import session
from models.models import Imagem, Processamento


router = APIRouter(prefix="/processamentos", tags=["Processamentos"])


def serialize(item):
    return ProcessamentoLeitura.model_validate(item)

@router.post("/", status_code=201, response_model=ProcessamentoLeitura)
def criar(body: ProcessamentoCriacao, db: Session = Depends(session)):
    if db.get(Imagem, body.imagem_id) is None:
        raise HTTPException(404, "Imagem não encontrada")
    item = Processamento(imagem_id=body.imagem_id)
    db.add(item)
    db.flush()
    result = serialize(item)
    db.commit()
    return result

@router.get("/", response_model=list[ProcessamentoLeitura])
def listar(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(session)):
    return [serialize(item) for item in db.scalars(select(Processamento).order_by(Processamento.id).limit(limit).offset(offset))]

@router.get("/{processamento_id}", response_model=ProcessamentoLeitura)
def obter(processamento_id: int, db: Session = Depends(session)):
    item = db.get(Processamento, processamento_id)
    if item is None:
        raise HTTPException(404, "Processamento não encontrado")
    return serialize(item)
