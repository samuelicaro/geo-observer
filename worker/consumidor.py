"""Worker didático: recorta TIFFs; não executa inferência."""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from worker.tiles import recortar

from dotenv import load_dotenv
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from api.database import engine
from api.raster import original_local
from api.storage import storage
from models.models import Tarefa, Processamento, Imagem
from worker.broker import conectar, QUEUE

def executar(tarefa_id):
    with Session(engine()) as db, db.begin():
        tarefa = db.scalar(select(Tarefa).where(Tarefa.id == tarefa_id).with_for_update())
        if tarefa is None or tarefa.status in ("concluida", "falhou"):
            return True
        tarefa.tentativas += 1
        processo = db.get(Processamento, tarefa.processamento_id)
        imagem = db.get(Imagem, processo.imagem_id)
        try:
            with original_local(imagem) as path, TemporaryDirectory() as directory:
                output = Path(directory) / "tile.tif"
                recortar(path, output, tarefa)
                # Chave determinística: uma reentrega substitui o mesmo tile.
                key = f"tiles/{processo.id}/{tarefa.id}.tif"
                storage().fput_object(imagem.bucket, key, str(output), content_type="image/tiff")
            tarefa.status, tarefa.erro = "concluida", None
        except Exception as exc:
            logging.exception("Falha na tarefa %s", tarefa.id)
            tarefa.status = "falhou" if tarefa.tentativas >= 3 else "pendente"
            tarefa.erro = type(exc).__name__
        db.flush()
        # Serializa somente a atualização do resumo, após o trabalho pesado.
        processo = db.scalar(select(Processamento).where(Processamento.id == processo.id).with_for_update())
        counts = dict(db.execute(select(Tarefa.status, func.count()).where(
            Tarefa.processamento_id == processo.id).group_by(Tarefa.status)).all())
        pendentes = counts.get("pendente", 0) + counts.get("processando", 0)
        processo.status = "processando" if pendentes else ("falhou" if counts.get("falhou") else "concluido")
        return tarefa.status != "pendente"

def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s worker=%(process)d %(message)s")
    logging.getLogger("pika").setLevel(logging.WARNING)
    with ThreadPoolExecutor(max_workers=1) as executor:
        while True:
            connection = None
            try:
                connection, channel = conectar()
                def receber(ch, method, properties, body):
                    try:
                        task_id = json.loads(body)["tarefa_id"]
                        if type(task_id) is not int or task_id <= 0:
                            raise ValueError()
                    except (ValueError, KeyError, TypeError):
                        ch.basic_reject(method.delivery_tag, requeue=False)
                        return
                    logging.info("Recebida tarefa %s; reentrega=%s", task_id, method.redelivered)
                    future = executor.submit(executar, task_id)
                    # Mantém heartbeat ativo durante leitura e escrita do raster.
                    while not future.done():
                        connection.sleep(0.2)
                    finalizada = future.result()
                    logging.info("Tarefa %s: %s", task_id, "confirmada" if finalizada else "nova tentativa")
                    if finalizada:
                        ch.basic_ack(method.delivery_tag)
                    else:
                        connection.sleep(2)
                        ch.basic_nack(method.delivery_tag, requeue=True)
                channel.basic_consume(queue=QUEUE, on_message_callback=receber, auto_ack=False)
                channel.start_consuming()
            except Exception:
                logging.exception("Worker desconectado; aguardando reconexão")
                time.sleep(5)
            finally:
                if connection and connection.is_open:
                    connection.close()

if __name__ == "__main__":
    main()



