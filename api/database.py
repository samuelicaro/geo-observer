import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.models import Base

@lru_cache
def engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Configure DATABASE_URL")
    return create_engine(url, pool_pre_ping=True)

def session():
    with sessionmaker(bind=engine())() as db:
        yield db

if __name__ == "__main__":
    Base.metadata.create_all(engine())
