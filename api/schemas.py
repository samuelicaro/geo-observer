"""Contratos HTTP. Geometrias PostGIS não são expostas como WKB no JSON."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Leitura(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UsuarioLeitura(Leitura):
    id: int
    nome: str
    email: str
    criado_em: datetime
    # senha_hash nunca integra a resposta pública.


class ImagemLeitura(Leitura):
    id: int
    nome_original: str
    tamanho_bytes: int = Field(gt=0)
    largura_px: int | None = Field(default=None, gt=0)
    altura_px: int | None = Field(default=None, gt=0)
    crs: str | None = None


class ProcessamentoCriacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imagem_id: int = Field(gt=0)


class ProcessamentoLeitura(Leitura):
    id: int
    imagem_id: int
    status: Literal["aguardando_planejamento", "pendente", "processando", "concluido", "falhou"]
    criado_em: datetime


class TarefaLeitura(Leitura):
    id: int
    processamento_id: int
    coluna: int = Field(ge=0)
    linha: int = Field(ge=0)
    largura: int = Field(gt=0)
    altura: int = Field(gt=0)
    status: Literal["pendente", "processando", "concluida", "falhou"]
    tentativas: int = Field(ge=0)
    criado_em: datetime


class PoligonoLeitura(Leitura):
    """Metadados; conversão da geometria para GeoJSON fica para a etapa do mapa."""
    id: int
    tarefa_id: int
    classe: str
    confianca: float = Field(ge=0, le=1)
