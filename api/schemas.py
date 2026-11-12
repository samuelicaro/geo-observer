"""Contratos HTTP. Geometrias PostGIS não são expostas como WKB no JSON."""
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


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


class UsuarioCriacao(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nome: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    senha: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        return value.lower()


class PlanejamentoCriacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tamanho_tile: int = Field(default=512, ge=64, le=1024)


class GeometriaArea(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[tuple[float, float]]] = Field(min_length=1, max_length=1)

    @field_validator("coordinates")
    @classmethod
    def validar_anel(cls, rings):
        ring = rings[0]
        if not 4 <= len(ring) <= 201 or ring[0] != ring[-1]:
            raise ValueError("Envie um anel fechado com 3 a 200 vértices.")
        if len(set(ring[:-1])) != len(ring)-1:
            raise ValueError("O polígono possui vértices repetidos.")
        for lon, lat in ring:
            if not -180 <= lon <= 180 or not -85 <= lat <= 85:
                raise ValueError("Coordenadas fora dos limites do mapa.")
        if any(abs(a[0]-b[0]) > 180 for a,b in zip(ring,ring[1:])):
            raise ValueError("Não cruze o antimeridiano.")
        return rings


class AreaCriacao(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    nome: str = Field(min_length=1, max_length=100)
    imagem_id: int | None = Field(default=None, gt=0)
    geometria: GeometriaArea


class AreaLeitura(BaseModel):
    id: str
    nome: str
    imagem_id: int | None
    geometria: GeometriaArea
    criado_em: datetime
