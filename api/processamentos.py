from fastapi import APIRouter, Depends, HTTPException, Query
from api.schemas import ProcessamentoCriacao, ProcessamentoLeitura
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from api.database import session
from models.models import Imagem, Processamento, Tarefa


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

@router.delete("/{processamento_id}", response_model=ProcessamentoLeitura)
def remover(processamento_id: int, db: Session = Depends(session)):
    item = db.get(Processamento, processamento_id)
    if item is None:
        raise HTTPException(404, "Processamento não encontrado")

    vinculo = db.scalar(
        select(Tarefa.id).where(Tarefa.processamento_id == processamento_id).limit(1)
    )
    if vinculo is not None:
        raise HTTPException(409, "O processamento possui tarefas vinculadas e não pode ser removido.")

    resposta = ProcessamentoLeitura.model_validate(item)
    try:
        db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Cobre uma tarefa criada entre a consulta e a exclusão.
        if getattr(exc.orig, "sqlstate", None) in {"23502", "23503"}:
            raise HTTPException(409, "O processamento possui registros vinculados e não pode ser removido.") from None
        raise
    return resposta
