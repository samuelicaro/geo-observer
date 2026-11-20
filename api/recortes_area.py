"""Planeja janelas com pixels dentro da área, no CRS real do raster."""
import numpy as np
import rasterio
from rasterio.features import geometry_window,geometry_mask
from rasterio.warp import transform_geom
from rasterio.errors import WindowError
from rasterio.windows import Window
from fastapi import HTTPException

def planejar_area(path,geometry,tamanho):
    with rasterio.open(path) as src:
        geom=transform_geom('EPSG:4326',src.crs,geometry)
        try: extent=geometry_window(src,[geom])
        except WindowError:raise HTTPException(422,'A área não intersecta a imagem.') from None
        start_col,start_row=int(extent.col_off),int(extent.row_off)
        stop_col,stop_row=int(extent.col_off+extent.width),int(extent.row_off+extent.height)
        windows=[]
        for row in range(start_row,stop_row,tamanho):
            for col in range(start_col,stop_col,tamanho):
                w,h=min(tamanho,stop_col-col),min(tamanho,stop_row-row)
                mask=geometry_mask([geom],out_shape=(h,w),transform=src.window_transform(Window(col,row,w,h)),invert=True)
                if np.any(mask):windows.append(dict(coluna=col,linha=row,largura=w,altura=h))
                if len(windows)>10000:raise HTTPException(422,'Área limitada a 10000 tarefas; aumente o tamanho do tile.')
        if not windows:raise HTTPException(422,'A área não contém centros de pixels nesta resolução.')
        return windows
