import rasterio
from rasterio.windows import Window

def recortar(source, destination, tarefa):
    with rasterio.open(source) as src:
        window = Window(tarefa.coluna, tarefa.linha, tarefa.largura, tarefa.altura)
        if window.col_off + window.width > src.width or window.row_off + window.height > src.height:
            raise ValueError('Janela fora da imagem')
        profile = src.profile.copy()
        profile.update(width=tarefa.largura, height=tarefa.altura, transform=src.window_transform(window))
        with rasterio.open(destination, 'w', **profile) as dst:
            # Uma banda por vez para limitar o uso de memória.
            for band in range(1, src.count + 1):
                dst.write(src.read(band, window=window), band)
            dst.colorinterp = src.colorinterp
