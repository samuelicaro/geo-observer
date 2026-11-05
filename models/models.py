"""Modelos persistidos no PostgreSQL/PostGIS; uma única Base para todas as tabelas."""
from datetime import datetime, timezone
from sqlalchemy import (BigInteger, CheckConstraint, DateTime, Float, ForeignKey,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement


def agora():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    senha_hash: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    imagens: Mapped[list["Imagem"]] = relationship(back_populates="usuario")


class Imagem(Base):
    __tablename__ = "imagens"
    __table_args__ = (
        UniqueConstraint("bucket", "objeto_chave"),
        CheckConstraint("tamanho_bytes > 0"),
        CheckConstraint("largura_px > 0 AND altura_px > 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    nome_original: Mapped[str] = mapped_column(Text)
    bucket: Mapped[str] = mapped_column(Text)
    objeto_chave: Mapped[str] = mapped_column(Text)
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger)
    largura_px: Mapped[int | None] = mapped_column(Integer)
    altura_px: Mapped[int | None] = mapped_column(Integer)
    crs: Mapped[str | None] = mapped_column(Text)
    transformacao_afim: Mapped[list[float] | None] = mapped_column(JSONB)
    area_coberta: Mapped[WKBElement | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326))
    usuario: Mapped["Usuario | None"] = relationship(back_populates="imagens")
    processamentos: Mapped[list["Processamento"]] = relationship(back_populates="imagem")


class Processamento(Base):
    __tablename__ = "processamentos"
    __table_args__ = (CheckConstraint("status IN ('aguardando_planejamento', 'pendente', 'processando', 'concluido', 'falhou')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    imagem_id: Mapped[int] = mapped_column(ForeignKey("imagens.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="aguardando_planejamento")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    imagem: Mapped["Imagem"] = relationship(back_populates="processamentos")
    tarefas: Mapped[list["Tarefa"]] = relationship(back_populates="processamento")


class Tarefa(Base):
    """Janela em pixels da imagem original; o worker fará o recorte futuramente."""
    __tablename__ = "tarefas"
    __table_args__ = (
        UniqueConstraint("processamento_id", "coluna", "linha", "largura", "altura"),
        CheckConstraint("coluna >= 0 AND linha >= 0 AND largura > 0 AND altura > 0"),
        CheckConstraint("tentativas >= 0"),
        CheckConstraint("status IN ('pendente', 'processando', 'concluida', 'falhou')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    processamento_id: Mapped[int] = mapped_column(ForeignKey("processamentos.id"), index=True)
    coluna: Mapped[int] = mapped_column(Integer)
    linha: Mapped[int] = mapped_column(Integer)
    largura: Mapped[int] = mapped_column(Integer)
    altura: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pendente")
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    processamento: Mapped["Processamento"] = relationship(back_populates="tarefas")
    poligonos: Mapped[list["Poligono"]] = relationship(back_populates="tarefa")


class Poligono(Base):
    __tablename__ = "poligonos"
    __table_args__ = (CheckConstraint("confianca >= 0 AND confianca <= 1"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefas.id"), index=True)
    classe: Mapped[str] = mapped_column(String(100))
    confianca: Mapped[float] = mapped_column(Float)
    geometria: Mapped[WKBElement] = mapped_column(Geometry("POLYGON", srid=4326))
    tarefa: Mapped["Tarefa"] = relationship(back_populates="poligonos")
