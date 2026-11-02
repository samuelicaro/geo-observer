from datetime import datetime
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Column, String, Integer, Text, ForeignKey, BigInteger, DateTime
import geoalchemy
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String)
    senha_hash: Mapped[Text] = mapped_column(Text)
    criado_em: Mapped[DateTime] = mapped_column(DateTime)

class Imagem(Base):
    __tablename__ = "imagens"
    id = Column("id", Integer, primary_key=True, autoincrement=True)
    usuario_id = Column("usuario_id", ForeignKey("usuarios.id")) # usuario que enviou a imagem
    nome_original = Column("nome_original", Text) # nome do arquivo enviado
    bucket = Column("bucket", Text)
    objeto_chave = Column("objeto_chave", Text)
    tamanho_bytes = Column("tamanho_bytes", BigInteger)
    largura_px = Column("largura_px", Integer)
    altura_px = Column("altura_px", Integer)
    crs = Column("crs", Text)
    transformacao_afim = Column("transformacao_afim", JSONB)
    area_coberta = Column("area_coberta", geoalchemy.geometry)
