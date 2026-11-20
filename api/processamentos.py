from fastapi import APIRouter, Depends, HTTPException, Query
from api.schemas import ProcessamentoCriacao, ProcessamentoLeitura
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from api.acesso import session
from models.models import Imagem, Processamento, Tarefa, EnvioTarefa, Poligono, AreaInteresse, EscopoProcessamento
from api.schemas import PlanejamentoCriacao, TarefaLeitura
from api.raster import original_local, metadados, janelas


router = APIRouter(prefix="/processamentos", tags=["Processamentos"])


def serialize(item):
    return ProcessamentoLeitura.model_validate(item)

@router.post("/", status_code=201, response_model=ProcessamentoLeitura)
def criar(body: ProcessamentoCriacao, db: Session = Depends(session)):
    if db.get(Imagem, body.imagem_id) is None:
        raise HTTPException(404, "Imagem não encontrada")
    snapshot=None
    if body.area_id is not None:
        from api.areas import serializar
        area=db.get(AreaInteresse,str(body.area_id))
        if area is None:raise HTTPException(404,'Área não encontrada')
        if area.imagem_id!=body.imagem_id:
            raise HTTPException(422,'Salve a área vinculada à imagem escolhida antes de analisar.')
        snapshot=serializar(area,db).model_dump(mode='json')
    item = Processamento(imagem_id=body.imagem_id)
    db.add(item)
    db.flush()
    if snapshot is not None:db.add(EscopoProcessamento(processamento_id=item.id,dados=snapshot))
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
        scope=db.get(EscopoProcessamento,item.id)
        if scope is not None:
            from api.recortes_area import planejar_area
            windows=planejar_area(path,scope.dados['geometria'],body.tamanho_tile)
        else:windows=None
    for key, value in dados.items():
        setattr(imagem, key, value)
    total = ((imagem.largura_px + body.tamanho_tile - 1) // body.tamanho_tile) * ((imagem.altura_px + body.tamanho_tile - 1) // body.tamanho_tile)
    if windows is None and total > 10000:
        raise HTTPException(422, "Planejamento limitado a 10000 tarefas; aumente o tamanho do tile.")
    for janela in (windows if windows is not None else janelas(imagem.largura_px, imagem.altura_px, body.tamanho_tile)):
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


@router.get("/{processamento_id}/resultados")
def resultados(processamento_id: int, limit: int = Query(1000,ge=1,le=5000), offset: int = Query(0,ge=0), db: Session = Depends(session)):
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping
    if db.get(Processamento,processamento_id) is None:
        raise HTTPException(404,"Processamento não encontrado")
    rows=list(db.scalars(select(Poligono).join(Tarefa).where(Tarefa.processamento_id==processamento_id).order_by(Poligono.id).limit(limit+1).offset(offset)))
    return {"type":"FeatureCollection","mais":len(rows)>limit,"offset":offset,"features":[
        {"type":"Feature","geometry":mapping(to_shape(p.geometria)),"properties":{"id":p.id,"classe":p.classe,"confianca":p.confianca}}
        for p in rows[:limit]]}


@router.get('/{processamento_id}/area')
def area_processamento(processamento_id: int, db: Session = Depends(session)):
    if db.get(Processamento,processamento_id) is None:raise HTTPException(404,'Processamento não encontrado')
    scope=db.get(EscopoProcessamento,processamento_id)
    return {'modo':'area' if scope else 'imagem_inteira','area':scope.dados if scope else None}
