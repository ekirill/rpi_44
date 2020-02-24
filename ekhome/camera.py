#!/usr/bin/env python3
import time
import logging
import psutil
import os

from YaDiskClient.YaDiskClient import YaDiskException

from ya_disk import Client


logging.basicConfig()
logging.root.setLevel(logging.DEBUG)
logger = logging.getLogger('ekhome_camera')


MEDIA_FOLDER = '/var/lib/motion/'
TRASH_FOLDER = os.path.join(MEDIA_FOLDER, 'trash')
DISK_FOLDER = 'HOME/CAMERA'


def file_is_free(fpath):
    # if any process has file handle opened for this file, than it is not free
    for proc in psutil.process_iter():
        try:
            for item in proc.open_files():
                if fpath == item.path:
                    return False
        except Exception:
            pass

    return True


def get_new_media(path):
    media = []
    for _, _, files in os.walk(path):
        for file in files:
            filename = os.path.join(path, file)
            if file_is_free(filename):
                media.append(filename)

        # just root folder is needed
        break

    return media


def upload_media(disk_client, filename):
    file_base_name = filename.split('/')[-1]

    dst = os.path.join(DISK_FOLDER, file_base_name)
    disk_client.upload(filename, dst)
    logger.info('Uploaded `{}` to `{}`'.format(file_base_name, dst))
    os.rename(filename, os.path.join(TRASH_FOLDER, file_base_name))


if __name__ == '__main__':
    login = os.getenv('EKIRILL_YADISK_LOGIN')
    password = os.getenv('EKIRILL_YADISK_PASSWORD')
    disk_client = Client(login, password)
    while True:
        new_media = get_new_media(MEDIA_FOLDER)
        for filename in new_media:
            upload_media(disk_client, filename)
        time.sleep(1)
