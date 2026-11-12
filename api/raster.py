from contextlib import contextmanager
from tempfile import TemporaryDirectory
from pathlib import Path
import shutil
import rasterio
from rasterio.warp import transform_bounds
from geoalchemy2.elements import WKTElement
from fastapi import HTTPException
from api.storage import storage

@contextmanager
def original_local(imagem):
    with TemporaryDirectory() as directory:
        path = Path(directory) / "original.tif"
        storage().fget_object(imagem.bucket, imagem.objeto_chave, str(path))
        yield path

def metadados(file):
    if hasattr(file, "read"):
        # Rasterio pode copiar um file-like inteiro para memória; usamos caminho local.
        with TemporaryDirectory() as directory:
            path = Path(directory) / "upload.tif"
            file.seek(0)
            with path.open("wb") as output:
                shutil.copyfileobj(file, output, length=1024 * 1024)
            file.seek(0)
            return metadados(path)
    try:
        with rasterio.open(file, driver="GTiff") as src:
            if not src.crs:
                raise HTTPException(422, "O TIFF precisa ter um sistema de coordenadas (CRS).")
            west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            area = WKTElement(f"MULTIPOLYGON((({west} {south},{east} {south},{east} {north},{west} {north},{west} {south})))", srid=4326)
            return dict(area_coberta=area, largura_px=src.width, altura_px=src.height,
                        crs=src.crs.to_string(), transformacao_afim=list(src.transform)[:6])
    except rasterio.errors.RasterioError as exc:
        raise HTTPException(422, "GeoTIFF inválido ou não suportado.") from exc

def janelas(largura, altura, tamanho):
    for linha in range(0, altura, tamanho):
        for coluna in range(0, largura, tamanho):
            yield dict(coluna=coluna, linha=linha,
                       largura=min(tamanho, largura-coluna),
                       altura=min(tamanho, altura-linha))



