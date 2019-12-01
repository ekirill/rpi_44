#!/usr/bin/env python3.5
import os
import time
import pika

RABBIT_HOST = os.getenv('LIGHTER_RABBIT_HOST', 'localhost')
RABBIT_QUEUE = os.getenv('LIGHTER_RABBIT_QUEUE')
RABBIT_USER = os.getenv('LIGHTER_RABBIT_USER')
RABBIT_PASSWORD = os.getenv('LIGHTER_RABBIT_PASSOWRD')

credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASSWORD)
parameters = pika.ConnectionParameters(RABBIT_HOST, 5672, '/', credentials)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()

channel.queue_delete(queue=RABBIT_QUEUE)
channel.queue_declare(queue=RABBIT_QUEUE, arguments={"x-max-length": 5})

if __name__ == '__main__':
    try:
        while True:
            msg = str(int(time.time()))
            channel.basic_publish(exchange='', routing_key=RABBIT_QUEUE, body=msg)
            print(msg)
            time.sleep(1)
    finally:
        connection.close()
