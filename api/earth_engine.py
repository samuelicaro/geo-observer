"""Aquisição de cenas pequenas Sentinel-2. Credenciais ficam no servidor."""
from datetime import date, timedelta
from functools import lru_cache
import os
from tempfile import SpooledTemporaryFile
from urllib.request import urlopen
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session
from api.database import session
from api.imagens import persistir
from api.schemas import ImagemLeitura

COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
BANDS = ["B4", "B3", "B2", "B8"]
router = APIRouter(prefix="/satelite", tags=["Satélite"])

class Area(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    oeste: float = Field(ge=-180, le=180)
    sul: float = Field(ge=-60, le=60)
    leste: float = Field(ge=-180, le=180)
    norte: float = Field(ge=-60, le=60)

    @model_validator(mode="after")
    def validar(self):
        if self.oeste >= self.leste or self.sul >= self.norte:
            raise ValueError("Selecione um retângulo válido, sem cruzar o antimeridiano.")
        # Limite conservador de 5 km por lado, abaixo do download interativo.
        if (self.leste-self.oeste)*111.32 > 5 or (self.norte-self.sul)*111.32 > 5:
            raise ValueError("Selecione uma área menor: até aproximadamente 5 km por lado.")
        return self

    def coords(self):
        return [self.oeste, self.sul, self.leste, self.norte]

class Busca(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area: Area
    inicio: date
    fim: date
    nuvens: int = Field(default=30, ge=0, le=100)

    @model_validator(mode="after")
    def validar(self):
        if not 0 <= (self.fim-self.inicio).days <= 366:
            raise ValueError("O intervalo deve estar ordenado e ter até 366 dias.")
        return self

class Cena(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area: Area
    cena_id: str = Field(pattern=r"^COPERNICUS/S2_SR_HARMONIZED/[A-Za-z0-9_]+$", max_length=180)

@lru_cache
def cliente():
    project = os.environ.get("EE_PROJECT")
    if not project:
        raise HTTPException(503, "Configure EE_PROJECT e autentique o Earth Engine no servidor.")
    import ee
    try:
        key = os.environ.get("EE_SERVICE_ACCOUNT_FILE")
        if key:
            ee.Initialize(ee.ServiceAccountCredentials(os.environ["EE_SERVICE_ACCOUNT_EMAIL"], key), project=project)
        else:
            ee.Initialize(project=project)
        ee.data.setDeadline(60000)
        return ee
    except Exception as exc:
        raise HTTPException(503, "Earth Engine não autenticado ou projeto sem acesso. Confira a configuração local.") from exc

def geometria(ee, area):
    return ee.Geometry.Rectangle(area.coords(), proj="EPSG:4326", geodesic=False)

def selecionar(body):
    ee = cliente()
    try:
        image = ee.Image(body.cena_id)
        region = geometria(ee, body.area)
        if not image.geometry().intersects(region, 1).getInfo():
            raise HTTPException(422, "A cena não cobre a área selecionada.")
        return ee, image, region
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Não foi possível acessar essa cena no Earth Engine.") from exc

@router.get("/config")
def config():
    return {"configurado": bool(os.environ.get("EE_PROJECT")), "colecao": COLLECTION, "resolucao_m":10}

@router.post("/buscar")
def buscar(body: Busca):
    ee = cliente()
    try:
        collection = (ee.ImageCollection(COLLECTION).filterBounds(geometria(ee,body.area))
                      .filterDate(body.inicio.isoformat(),(body.fim+timedelta(days=1)).isoformat())
                      .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE",body.nuvens))
                      .sort("system:time_start", False).limit(10))
        info = collection.getInfo()
        return [{"id":f["id"], "data":f["properties"]["system:time_start"],
                 "nuvens":f["properties"].get("CLOUDY_PIXEL_PERCENTAGE"), "resolucao_m":10}
                for f in info.get("features",[])]
    except Exception as exc:
        raise HTTPException(502, "Falha na busca do Earth Engine. Confira acesso e tente novamente.") from exc

@router.post("/previa")
def previa(body: Cena):
    ee, image, region = selecionar(body)
    try:
        tiles=image.clip(region).getMapId({"bands":["B4","B3","B2"],"min":0,"max":3000})
        return {"tile_url":tiles["tile_fetcher"].url_format}
    except Exception as exc:
        raise HTTPException(502, "Não foi possível gerar a camada da cena.") from exc

@router.post("/importar", status_code=201, response_model=ImagemLeitura)
def importar(body: Cena, db: Session = Depends(session)):
    ee, image, region = selecionar(body)
    try:
        props=image.toDictionary(["system:time_start","CLOUDY_PIXEL_PERCENTAGE"]).getInfo()
        # UTM local para conservar resolução em metros.
        lon=(body.area.oeste+body.area.leste)/2
        zone=min(60,max(1,int((lon+180)//6)+1))
        crs=f"EPSG:{(32600 if body.area.sul>=0 else 32700)+zone}"
        url=image.select(BANDS).clip(region).getDownloadURL({
            "region":region,"scale":10,"crs":crs,"format":"GEO_TIFF","filePerBand":False})
        with urlopen(url, timeout=90) as response, SpooledTemporaryFile(max_size=8*1024*1024) as file:
            size=0
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                if size>32*1024*1024:
                    raise HTTPException(413,"Recorte acima de 32 MB; selecione área menor.")
                file.write(chunk)
            file.seek(0)
            origem={"provedor":"Earth Engine","colecao":COLLECTION,"cena_id":body.cena_id,
                    "aquisicao_ms":props.get("system:time_start"),"nuvens_cena":props.get("CLOUDY_PIXEL_PERCENTAGE"),
                    "area":body.area.model_dump(),"bandas":BANDS,"escala_m":10,
                    "crs_exportacao":crs,"valores":"reflectância escalada por 10000; sem ajuste da prévia"}
            return persistir(file,body.cena_id.rsplit("/",1)[1]+".tif",size,db,origem=origem)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(502,"Falha ao importar cena. Confira a lista de imagens antes de repetir.") from exc

