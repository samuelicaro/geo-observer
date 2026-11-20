"""Sessões revogáveis: apenas hash do token fica no banco."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256, scrypt
from secrets import token_urlsafe, compare_digest
import os
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from api.database import engine
from models.models import Usuario, SessaoUsuario
from api.schemas import UsuarioLeitura

router=APIRouter(prefix='/auth', tags=['Autenticação'])
COOKIE='geo_sessao'

def usuario_atual(request: Request):
    token=request.cookies.get(COOKIE,'')
    if not token or len(token)>200: raise HTTPException(401,'Entre na sua conta.')
    with Session(engine()) as db:
        row=db.get(SessaoUsuario,sha256(token.encode()).hexdigest())
        if row is None or row.expira_em <= datetime.now(timezone.utc):
            raise HTTPException(401,'Sessão inválida ou expirada.')
        user=db.get(Usuario,row.usuario_id)
        if user is None: raise HTTPException(401,'Sessão inválida.')
        return UsuarioLeitura.model_validate(user)

def verificar_senha(senha, stored):
    try:
        kind,n,r,p,salt,digest=stored.split('$')
        if (kind,n,r,p)!=('scrypt','16384','8','1'): return False
        actual=scrypt(senha.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1)
        return compare_digest(actual,bytes.fromhex(digest))
    except (ValueError,TypeError): return False

class Login(BaseModel):
    email: str = Field(max_length=254)
    senha: SecretStr = Field(min_length=1,max_length=128)

@router.post('/entrar',response_model=UsuarioLeitura)
def entrar(body: Login, request: Request, response: Response):
    with Session(engine()) as db:
        user=db.scalar(select(Usuario).where(Usuario.email==body.email.strip().lower()))
        # Mesmo custo de hash para e-mail desconhecido.
        stored=user.senha_hash if user else 'scrypt$16384$8$1$'+'00'*16+'$'+'00'*64
        if not verificar_senha(body.senha.get_secret_value(),stored) or user is None:
            raise HTTPException(401,'E-mail ou senha inválidos.')
        result=criar_sessao(db,user,request,response)
        db.commit()
    return result


def criar_sessao(db, user, request, response):
    old=request.cookies.get(COOKIE)
    if old:
        previous=db.get(SessaoUsuario,sha256(old.encode()).hexdigest())
        if previous: db.delete(previous)
    token=token_urlsafe(32)
    db.add(SessaoUsuario(token_hash=sha256(token.encode()).hexdigest(),usuario_id=user.id,
                        expira_em=datetime.now(timezone.utc)+timedelta(hours=8)))
    response.set_cookie(COOKIE,token,max_age=28800,httponly=True,samesite='strict',
                        secure=os.environ.get('COOKIE_SECURE','false').lower()=='true')
    response.headers['Cache-Control']='no-store'
    return UsuarioLeitura.model_validate(user)

@router.get('/eu',response_model=UsuarioLeitura)
def eu(user=Depends(usuario_atual)): return user

@router.post('/sair',status_code=204)
def sair(request: Request, response: Response):
    token=request.cookies.get(COOKIE,'')
    with Session(engine()) as db:
        row=db.get(SessaoUsuario,sha256(token.encode()).hexdigest())
        if row: db.delete(row); db.commit()
    response.delete_cookie(COOKIE)
