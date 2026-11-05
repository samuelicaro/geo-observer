"""Prévia reduzida; não altera os valores do raster original."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.errors import RasterioError
from PIL import Image
from fastapi import HTTPException
from api.storage import storage

_slots = BoundedSemaphore(1)

def gerar_previa(item):
    if not _slots.acquire(blocking=False):
        raise HTTPException(503, 'Outra prévia está sendo gerada. Tente novamente em instantes.')
    try:
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'imagem.tif'
            client = storage()
            response = client.get_object(item.bucket, item.objeto_chave)
            try:
                with path.open('wb') as target:
                    size = 0
                    for chunk in response.stream(1024 * 1024):
                        size += len(chunk)
                        if size > 512 * 1024 * 1024:
                            raise HTTPException(413, 'Prévia limitada a arquivos de até 512 MB.')
                        target.write(chunk)
            finally:
                response.close()
                response.release_conn()
            try:
                with rasterio.Env(GDAL_CACHEMAX=64 * 1024 * 1024):
                    with rasterio.open(path, driver='GTiff') as src:
                        colors = list(src.colorinterp)
                        rgb = (ColorInterp.red, ColorInterp.green, ColorInterp.blue)
                        bands = [colors.index(c) + 1 for c in rgb] if all(c in colors for c in rgb) else ([1, 2, 3] if src.count >= 3 else [1])
                        scale = min(1, 1200 / max(src.width, src.height))
                        h, w = max(1, round(src.height * scale)), max(1, round(src.width * scale))
                        pixels = src.read(bands, out_shape=(len(bands), h, w), masked=True, resampling=Resampling.nearest)
                        channels = []
                        valid = ~np.ma.getmaskarray(pixels).any(axis=0)
                        for band in pixels:
                            arr = band.filled(0).astype('float64')
                            good = ~np.ma.getmaskarray(band) & np.isfinite(arr)
                            valid &= good
                            if band.dtype != np.uint8 and good.any():
                                low, high = np.percentile(arr[good], [2, 98])
                                arr = (arr - low) * 255 / (high - low) if high > low else np.full_like(arr, 127)
                            channels.append(np.clip(np.nan_to_num(arr), 0, 255).astype('uint8'))
                        if len(channels) == 1:
                            channels *= 3
                        rgba = np.stack([*channels, valid.astype('uint8') * 255], axis=-1)
                        output = BytesIO()
                        Image.fromarray(rgba).save(output, format='PNG')
                        return output.getvalue()
            except (RasterioError, ValueError) as exc:
                raise HTTPException(422, 'Não foi possível gerar prévia deste TIFF.') from exc
    finally:
        _slots.release()
