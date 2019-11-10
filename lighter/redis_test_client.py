#!/usr/bin/env python3.5
import logging
import os
import time
from redis import StrictRedis

REDIS_HOST = os.getenv('LIGHTER_REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('LIGHTER_REDIS_PORT', '6379'))
REDIS_LIGHTER_STATUS_KEY = 'LIGHTER_STATUS'

client = StrictRedis(host=REDIS_HOST, port=REDIS_PORT)
pubsub = client.pubsub()

def event_handler(msg):
    if msg.get('data', '').decode('ascii').lower() == 'set':
        raw_value = client.get(REDIS_LIGHTER_STATUS_KEY)
        try:
            value = int(raw_value)
            print('New value is ', value)
        except (TypeError, ValueError):
            logging.error('Value is updated, but it is not INT: {}'.format(raw_value))


subscribe_filter = '__keyspace@0__:{}'.format(REDIS_LIGHTER_STATUS_KEY)
pubsub.psubscribe(**{subscribe_filter: event_handler})
thread = pubsub.run_in_thread(sleep_time=0.1)


if __name__ == '__main__':
    try:
        i = 0
        while True:
            i += 1
            print(i)
            time.sleep(3)
    finally:
        pubsub.close()
