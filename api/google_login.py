"""Google Identity Services: callback JS, nonce de uso único e sessão local."""
import os
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from secrets import token_urlsafe,compare_digest
from typing import Literal
from functools import partial
from fastapi import APIRouter,HTTPException,Request,Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport.requests import Request as GoogleRequest
from google.auth.exceptions import TransportError
from api.database import engine
from api.auth import usuario_atual,criar_sessao,COOKIE
from api.schemas import UsuarioLeitura
from models.models import Usuario,IdentidadeGoogle,DesafioGoogle

router=APIRouter(prefix='/auth/google',tags=['Login Google'])
CHALLENGE_COOKIE='geo_google_desafio'

def digest(value): return sha256(value.encode()).hexdigest()

def client_id():
    value=os.environ.get('GOOGLE_CLIENT_ID','').strip()
    if not value: raise HTTPException(503,'Login Google ainda não configurado. Use a entrada com senha.')
    return value

@router.get('/config')
def config():
    value=os.environ.get('GOOGLE_CLIENT_ID','').strip()
    return {'disponivel':bool(value),'client_id':value or None}

class Inicio(BaseModel):
    model_config=ConfigDict(extra='forbid')
    modo: Literal['entrar','vincular']='entrar'

class Credencial(BaseModel):
    model_config=ConfigDict(extra='forbid')
    credential: str = Field(min_length=1,max_length=16384)

@router.post('/iniciar')
def iniciar(body: Inicio,request: Request,response: Response):
    cid=client_id()
    user=usuario_atual(request) if body.modo=='vincular' else None
    token,nonce=token_urlsafe(32),token_urlsafe(32)
    with Session(engine()) as db,db.begin():
        db.execute(delete(DesafioGoogle).where(DesafioGoogle.expira_em < datetime.now(timezone.utc)))
        old=request.cookies.get(CHALLENGE_COOKIE)
        if old: db.execute(delete(DesafioGoogle).where(DesafioGoogle.token_hash==digest(old)))
        db.add(DesafioGoogle(token_hash=digest(token),nonce_hash=digest(nonce),modo=body.modo,
            usuario_id=user.id if user else None,sessao_hash=digest(request.cookies.get(COOKIE,'')) if user else None,
            expira_em=datetime.now(timezone.utc)+timedelta(minutes=10)))
    response.set_cookie(CHALLENGE_COOKIE,token,max_age=600,httponly=True,samesite='strict',
        secure=os.environ.get('COOKIE_SECURE','false').lower()=='true')
    return {'client_id':cid,'nonce':nonce}

def verificar(credential,cid):
    try:
        claims=id_token.verify_oauth2_token(credential,partial(GoogleRequest(),timeout=10),cid)
    except TransportError as exc:
        raise HTTPException(503,'Google indisponível. Tente novamente ou use sua senha.') from exc
    except ValueError as exc:
        raise HTTPException(401,'Credencial Google inválida ou expirada.') from exc
    if (claims.get('aud')!=cid or claims.get('iss') not in ('accounts.google.com','https://accounts.google.com')
        or claims.get('email_verified') is not True or not isinstance(claims.get('sub'),str)
        or not 1<=len(claims['sub'])<=255):
        raise HTTPException(401,'Identidade Google inválida.')
    email=claims.get('email','')
    if not isinstance(email,str) or not 3<=len(email)<=254 or '@' not in email:
        raise HTTPException(401,'E-mail Google inválido.')
    return claims

@router.post('/concluir',response_model=UsuarioLeitura)
def concluir(body: Credencial,request: Request,response: Response):
    cid=client_id()
    token=request.cookies.get(CHALLENGE_COOKIE,'')
    if not token or len(token)>200: raise HTTPException(401,'Reabra o login Google para iniciar uma nova tentativa.')
    try:
        with Session(engine()) as db,db.begin():
            challenge=db.scalar(select(DesafioGoogle).where(DesafioGoogle.token_hash==digest(token)).with_for_update())
            if challenge is None or challenge.expira_em<=datetime.now(timezone.utc):
                raise HTTPException(401,'Tentativa expirada ou já utilizada. Reabra o login Google.')
            claims=verificar(body.credential,cid)
            nonce=claims.get('nonce')
            if not isinstance(nonce,str) or not compare_digest(digest(nonce),challenge.nonce_hash):
                raise HTTPException(401,'Tentativa Google não corresponde a este navegador.')
            identity=db.get(IdentidadeGoogle,claims['sub'])
            if challenge.modo=='vincular':
                current=usuario_atual(request)
                if current.id!=challenge.usuario_id or not compare_digest(digest(request.cookies.get(COOKIE,'')),challenge.sessao_hash):
                    raise HTTPException(401,'Sua sessão mudou. Recomece a vinculação.')
                if identity is not None and identity.usuario_id!=current.id:
                    raise HTTPException(409,'Essa identidade Google já pertence a outra conta.')
                other=db.scalar(select(IdentidadeGoogle).where(IdentidadeGoogle.usuario_id==current.id))
                if other is not None and other.sub!=claims['sub']:
                    raise HTTPException(409,'Sua conta já está vinculada a outra identidade Google.')
                user=db.get(Usuario,current.id)
                if identity is None: db.add(IdentidadeGoogle(sub=claims['sub'],usuario_id=user.id))
            elif identity is not None:
                user=db.get(Usuario,identity.usuario_id)
            else:
                email=claims['email'].strip().lower()
                if db.scalar(select(Usuario.id).where(Usuario.email==email)) is not None:
                    raise HTTPException(409,'Já existe uma conta com esse e-mail. Entre com sua senha e use Vincular Google para preservar seus dados.')
                name=claims.get('name')
                user=Usuario(nome=(name.strip()[:100] if isinstance(name,str) and name.strip() else 'Usuário Google'),email=email,senha_hash='google-only')
                db.add(user);db.flush()
                db.add(IdentidadeGoogle(sub=claims['sub'],usuario_id=user.id))
            result=criar_sessao(db,user,request,response)
            db.delete(challenge)
        response.delete_cookie(CHALLENGE_COOKIE)
        return result
    except IntegrityError as exc:
        raise HTTPException(409,'Conta alterada durante o login. Recomece e confira o vínculo existente.') from exc
