import os
from functools import lru_cache
from minio import Minio

@lru_cache
def storage():
    return Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=os.environ.get("MINIO_SECURE", "true").lower() == "true",
    )

def bucket():
    return os.environ.get("MINIO_BUCKET", "imagens")
