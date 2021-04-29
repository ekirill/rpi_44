#!/usr/bin/env python3
import time
import logging
import psutil
import os

from webdav import Client

logger = logging.getLogger('ekhome_camera')
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(levelname)s\t%(asctime)s\t%(message)s')
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)


MAX_RETRY_DELAY = 30 * 60

MEDIA_FOLDER = os.getenv('EKIRILL_MEDIA_FOLDER', 'CAMERA')
TRASH_FOLDER = os.path.join(MEDIA_FOLDER, 'trash')
DAV_FOLDER = os.getenv('EKIRILL_WEBDAV_FOLDER', 'CAMERA')
MAX_TRASH_SIZE = 500 * 1024 * 1024
EXCLUDE_CONTAINS = ('lastsnap', )


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


def get_new_media(path, exclude_dir=None, exclude_contains=None):
    media = []

    if exclude_dir is None:
        exclude_dir = []
    if exclude_contains is None:
        exclude_contains = []

    for dirpath, _, files in os.walk(path):
        if dirpath == path:
            # skipping root dir
            continue

        if dirpath in exclude_dir:
            continue

        for file in files:
            if any(excl in file for excl in EXCLUDE_CONTAINS):
                continue

            filename = os.path.join(dirpath, file)
            if file_is_free(filename):
                media.append((dirpath.split("/")[-1], file))

    return media


def upload_media(disk_client, base_folder, camera_name, filename):
    dav_folder = DAV_FOLDER.replace("{{ name }}", camera_name)
    dst = os.path.join(dav_folder, filename)
    full_name = os.path.join(base_folder, camera_name, filename)
    disk_client.upload(full_name, dst)
    logger.info('Uploaded `{}` to `{}`'.format(full_name, dst))
    os.rename(full_name, os.path.join(TRASH_FOLDER, filename))


def validate_trash():
    total_size = 0
    trash_files = []
    for _, _, files in os.walk(TRASH_FOLDER):
        for file in files:
            filename = os.path.join(TRASH_FOLDER, file)
            statinfo = os.stat(filename)
            trash_files.append((filename, statinfo.st_mtime, statinfo.st_size))

        # just root folder is needed
        break

    trash_files = sorted(trash_files, key=lambda f: f[1], reverse=True)

    f_idx = 0
    for filename, _, f_size in trash_files:
        if total_size + f_size < MAX_TRASH_SIZE:
            total_size += f_size
            f_idx += 1
            continue
        else:
            break

    for idx in range(f_idx, len(trash_files)):
        filename, _, f_size = trash_files[idx]
        logger.info('Erasing old file from trash: `%s`', filename)
        os.unlink(filename)


if __name__ == '__main__':
    base_url = os.getenv('EKIRILL_WEBDAV_URL')
    login = os.getenv('EKIRILL_WEBDAV_LOGIN')
    password = os.getenv('EKIRILL_WEBDAV_PASSWORD')
    disk_client = Client(base_url, login, password)
    retry_delay = 1
    while True:
        new_media = get_new_media(MEDIA_FOLDER, exclude_dir=[TRASH_FOLDER], exclude_contains=EXCLUDE_CONTAINS)
        for camera_name, filename in new_media:
            try:
                upload_media(disk_client, MEDIA_FOLDER, camera_name, filename)
                retry_delay = 1
            except Exception as e:
                logger.error('Could not upload file `%s`: %r', filename, e)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                time.sleep(retry_delay)

            try:
                validate_trash()
            except Exception as e:
                logger.error('Could not clean trash folder: %r', e)

        time.sleep(1)
