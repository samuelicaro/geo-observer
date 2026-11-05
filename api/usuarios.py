from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from hashlib import scrypt
from secrets import token_bytes
from api.database import session
from api.schemas import UsuarioCriacao, UsuarioLeitura
from models.models import Usuario

router = APIRouter(prefix='/usuarios', tags=['Usuários'])

@router.post('/', status_code=201, response_model=UsuarioLeitura)
def cadastrar(body: UsuarioCriacao, db: Session = Depends(session)):
    salt = token_bytes(16)
    digest = scrypt(body.senha.get_secret_value().encode(), salt=salt, n=16384, r=8, p=1)
    senha_hash = f'scrypt$16384$8$1${salt.hex()}${digest.hex()}'
    usuario = Usuario(nome=body.nome, email=body.email, senha_hash=senha_hash)
    db.add(usuario)
    try:
        db.flush()
        resposta = UsuarioLeitura.model_validate(usuario)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, 'sqlstate', None) == '23505':
            raise HTTPException(409, 'E-mail já cadastrado') from None
        raise
    return resposta
