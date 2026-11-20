"""Deepness LandCover: RGB uint8, 512px, probabilidades de cinco classes."""
import os
from functools import lru_cache
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.features import shapes, sieve, geometry_mask
from rasterio.warp import transform_geom

CLASSES={1:'edificacao',2:'vegetacao_arborea',3:'agua',4:'via'}
EE_BANDS=['B4','B3','B2','B8']

def modo_entrada(src, origem):
    if src.count >= 3 and all(dtype=='uint8' for dtype in src.dtypes[:3]):
        return 'rgb_uint8'
    ee_reflectance=(
        origem is not None
        and origem.get('provedor')=='Earth Engine'
        and origem.get('bandas')==EE_BANDS
        and origem.get('escala_m')==10
        and 'reflectância escalada por 10000' in origem.get('valores','')
        and src.count==4
        and all(dtype=='uint16' for dtype in src.dtypes)
    )
    if ee_reflectance:
        return 'sentinel2_uint16'
    raise ValueError('O modelo aceita RGB uint8 ou cenas Sentinel-2 importadas pelo Earth Engine.')

def ler_rgb(src, window, modo):
    rgb=src.read([1,2,3],window=window)
    if modo=='sentinel2_uint16':
        # O Earth Engine exporta reflectância escalada por 10000; o modelo recebe RGB [0,1].
        rgb=np.rint(np.clip(rgb.astype('float32')/10000,0,1)*255).astype('uint8')
    return rgb

@lru_cache(maxsize=1)
def modelo():
    import onnxruntime as ort
    options=ort.SessionOptions()
    options.intra_op_num_threads=1
    options.inter_op_num_threads=1
    path=os.environ.get('ONNX_MODEL_PATH',str(Path(__file__).resolve().parents[1]/'modelos/deeplabv3_landcover_4c.onnx'))
    return ort.InferenceSession(path,sess_options=options,providers=['CPUExecutionProvider'])

def inferir(source, area=None, origem=None):
    session=modelo()
    with rasterio.open(source) as src:
        modo=modo_entrada(src,origem)
        if src.crs is None: raise ValueError('Imagem sem CRS')
        area_raster=transform_geom('EPSG:4326',src.crs,area) if area else None
        result=[]
        for row in range(0,src.height,512):
            for col in range(0,src.width,512):
                h,w=min(512,src.height-row),min(512,src.width-col)
                window=Window(col,row,w,h)
                rgb=ler_rgb(src,window,modo)
                valid=np.all(src.read_masks([1,2,3],window=window)>0,axis=0)
                if area_raster is not None:
                    valid &= geometry_mask([area_raster],out_shape=(h,w),transform=src.window_transform(window),invert=True)
                if not valid.any():continue
                rgb[:,~valid]=0
                x=np.pad(rgb,((0,0),(0,512-h),(0,512-w)),mode='edge').astype('float32')[None]/255.0
                probabilities=session.run(None,{session.get_inputs()[0].name:x})[0][0,:,:h,:w]
                labels=probabilities.argmax(axis=0).astype('uint8')
                confidence=probabilities.max(axis=0)
                labels[(confidence<0.5)|~valid]=0
                labels=sieve(labels,size=16,mask=valid)
                affine=src.window_transform(window)
                for geom,value in shapes(labels,mask=(labels>0)&valid,transform=affine):
                    cls=int(value)
                    # ConfianÃ§a resumida da classe na janela; nÃ£o Ã© acurÃ¡cia validada.
                    pixels=geometry_mask([geom],out_shape=(h,w),transform=affine,invert=True)&valid
                    score=float(probabilities[cls][pixels].mean())
                    geometry=transform_geom(src.crs,'EPSG:4326',geom)
                    if area is not None:
                        from shapely.geometry import shape,mapping
                        clipped=shape(geometry).intersection(shape(area))
                        parts=[clipped] if clipped.geom_type=='Polygon' else getattr(clipped,'geoms',[])
                        for part in parts:
                            if part.geom_type=='Polygon' and not part.is_empty and part.area>0:
                                result.append({'classe':CLASSES[cls],'confianca':score,'geometria':mapping(part)})
                    else:result.append({'classe':CLASSES[cls],'confianca':score,'geometria':geometry})
        return result
