import os
import pika

QUEUE = "geo_observer.tiles.v1"

def conectar():
    params = pika.URLParameters(os.environ["RABBITMQ_URL"])
    params.heartbeat = 60
    params.blocked_connection_timeout = 30
    params.socket_timeout = 10
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    return connection, channel

