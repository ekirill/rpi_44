#!/usr/bin/env python3.5
import os
import threading
import time

import pika


RABBIT_HOST = os.getenv('LIGHTER_RABBIT_HOST', 'localhost')
RABBIT_QUEUE = os.getenv('LIGHTER_RABBIT_QUEUE')
RABBIT_USER = os.getenv('LIGHTER_RABBIT_USER')
RABBIT_PASSWORD = os.getenv('LIGHTER_RABBIT_PASSWORD')

credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASSWORD)
parameters = pika.ConnectionParameters(RABBIT_HOST, 5672, '/', credentials)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()

channel.queue_delete(queue=RABBIT_QUEUE)
channel.queue_declare(queue=RABBIT_QUEUE, arguments={"x-max-length": 5})


def callback(ch, method, properties, body):
    print(" [x] Received %r" % body)
    channel.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_consume(callback, queue=RABBIT_QUEUE)

if __name__ == '__main__':

    try:
        thread = threading.Thread(target=channel.start_consuming, daemon=True)
        print('000')
        thread.start()
        print('111')
        time.sleep(2)
        print('222')
        time.sleep(999)
        print('FIN')
    finally:
        channel.stop_consuming()
        connection.close()
