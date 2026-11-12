from fastapi import APIRouter, Depends, HTTPException, Query
from api.schemas import ProcessamentoCriacao, ProcessamentoLeitura
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from api.database import session
from models.models import Imagem, Processamento, Tarefa, EnvioTarefa
from api.schemas import PlanejamentoCriacao, TarefaLeitura
from api.raster import original_local, metadados, janelas


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

@router.post("/{processamento_id}/planejar", response_model=ProcessamentoLeitura)
def planejar(processamento_id: int, body: PlanejamentoCriacao, db: Session = Depends(session)):
    item = db.scalar(select(Processamento).where(Processamento.id == processamento_id).with_for_update())
    if item is None:
        raise HTTPException(404, "Processamento não encontrado")
    if db.scalar(select(Tarefa.id).where(Tarefa.processamento_id == item.id).limit(1)):
        return serialize(item)  # Repetir a chamada não duplica tarefas.
    imagem = db.get(Imagem, item.imagem_id)
    with original_local(imagem) as path:
        dados = metadados(path)
    for key, value in dados.items():
        setattr(imagem, key, value)
    total = ((imagem.largura_px + body.tamanho_tile - 1) // body.tamanho_tile) * ((imagem.altura_px + body.tamanho_tile - 1) // body.tamanho_tile)
    if total > 10000:
        raise HTTPException(422, "Planejamento limitado a 10000 tarefas; aumente o tamanho do tile.")
    for janela in janelas(imagem.largura_px, imagem.altura_px, body.tamanho_tile):
        tarefa = Tarefa(processamento_id=item.id, **janela)
        db.add(tarefa)
        db.flush()
        db.add(EnvioTarefa(tarefa_id=tarefa.id))
    item.status = "pendente"
    db.flush()
    resposta = serialize(item)
    db.commit()
    return resposta

@router.get("/{processamento_id}/progresso")
def progresso(processamento_id: int, db: Session = Depends(session)):
    item = db.get(Processamento, processamento_id)
    if item is None:
        raise HTTPException(404, "Processamento não encontrado")
    counts = dict(db.execute(select(Tarefa.status, func.count()).where(Tarefa.processamento_id == item.id).group_by(Tarefa.status)).all())
    total = sum(counts.values())
    return {"id": item.id, "status": item.status, "total": total,
            "concluidas": counts.get("concluida", 0), "falhas": counts.get("falhou", 0),
            "percentual": round(100 * counts.get("concluida", 0) / total, 1) if total else 0}

@router.get("/{processamento_id}/tarefas", response_model=list[TarefaLeitura])
def tarefas(processamento_id: int, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(session)):
    if db.get(Processamento, processamento_id) is None:
        raise HTTPException(404, "Processamento não encontrado")
    return list(db.scalars(select(Tarefa).where(Tarefa.processamento_id == processamento_id).order_by(Tarefa.id).limit(limit).offset(offset)))
