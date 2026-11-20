"""Sessão HTTP isolada por usuário; workers usam Session(engine()) diretamente."""
from fastapi import Depends
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria
from api.auth import usuario_atual
from api.database import engine
from models.models import Imagem, AreaInteresse, Processamento, Tarefa, OrigemImagem, Poligono, EscopoProcessamento

def aplicar_escopo(db, usuario_id):
    db.info['usuario_id']=usuario_id
    images=select(Imagem.id).where(Imagem.usuario_id==usuario_id)
    tasks=select(Tarefa.id).where(Tarefa.processamento_id.in_(select(Processamento.id).where(Processamento.imagem_id.in_(images))))
    processes=select(Processamento.id).where(Processamento.imagem_id.in_(images))
    @event.listens_for(db,'do_orm_execute')
    def filtrar(state):
        if state.is_select:
            state.statement=state.statement.options(
                with_loader_criteria(EscopoProcessamento,EscopoProcessamento.processamento_id.in_(processes),include_aliases=True),
                with_loader_criteria(Poligono,Poligono.tarefa_id.in_(tasks),include_aliases=True),
                with_loader_criteria(Imagem,Imagem.usuario_id==usuario_id,include_aliases=True),
                with_loader_criteria(AreaInteresse,AreaInteresse.usuario_id==usuario_id,include_aliases=True),
                with_loader_criteria(Processamento,Processamento.imagem_id.in_(images),include_aliases=True),
                with_loader_criteria(Tarefa,Tarefa.processamento_id.in_(processes),include_aliases=True),
                with_loader_criteria(OrigemImagem,OrigemImagem.imagem_id.in_(images),include_aliases=True))
    @event.listens_for(db,'before_flush')
    def atribuir(session,context,instances):
        for obj in session.new:
            if isinstance(obj,(Imagem,AreaInteresse)): obj.usuario_id=usuario_id
    return db

def session(user=Depends(usuario_atual)):
    with Session(engine()) as db:
        aplicar_escopo(db,user.id)
        yield db
