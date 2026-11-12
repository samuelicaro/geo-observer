"""Outbox: confirmação do broker antes de marcar o envio no banco."""
import json
import logging
import time
import pika
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session
from api.database import engine
from models.models import EnvioTarefa, agora
from worker.broker import conectar, QUEUE

def publicar_lote(channel):
    channel.confirm_delivery()
    with Session(engine()) as db, db.begin():
        rows = db.scalars(select(EnvioTarefa).where(EnvioTarefa.publicado_em.is_(None))
                          .order_by(EnvioTarefa.tarefa_id).limit(50)
                          .with_for_update(skip_locked=True)).all()
        for row in rows:
            channel.basic_publish(exchange="", routing_key=QUEUE,
                body=json.dumps({"tarefa_id": row.tarefa_id}),
                properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
                mandatory=True)
            row.publicado_em = agora()
        return len(rows)

def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s publicador=%(process)d %(message)s")
    logging.getLogger("pika").setLevel(logging.WARNING)
    while True:
        connection = None
        try:
            connection, channel = conectar()
            while True:
                quantidade = publicar_lote(channel)
                if quantidade:
                    logging.info("Publicadas %s tarefas", quantidade)
                connection.sleep(2)
        except Exception:
            logging.exception("Publicador indisponível; nova tentativa em 5 segundos")
            time.sleep(5)
        finally:
            if connection and connection.is_open:
                connection.close()

if __name__ == "__main__":
    main()


