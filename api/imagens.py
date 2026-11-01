from fastapi import APIRouter

router = APIRouter(prefix="/imagens", tags=["Imagens"])

@router.get("/")
def get_imagens():
    return {"imagem1":"/home/documents/imagem1.tiff"}
