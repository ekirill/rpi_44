import logging
import os

from requests import request

logger = logging.getLogger('ekhome_camera')


class WebDavException(Exception):
    pass


class ProgressNotifier(object):
    def __init__(self, filename, chunksize=512 * 1024):
        self.filename = filename
        self.chunksize = chunksize
        self.totalsize = os.path.getsize(filename)
        self.readsofar = 0

    def __iter__(self):
        with open(self.filename, 'rb') as file:
            while True:
                data = file.read(self.chunksize)
                if not data:
                    logger.info("`{filename}` all read".format(filename=self.filename))
                    break
                self.readsofar += len(data)
                percent = self.readsofar * 100 / self.totalsize
                logger.info("`{filename}` {percent:3.0f}%".format(percent=percent, filename=self.filename))
                yield data

    def __len__(self):
        return self.totalsize


class Client(object):
    login = None
    password = None
    namespaces = {'d': 'DAV:'}

    def __init__(self, base_url,  login, password):
        super(Client, self).__init__()
        self.url = base_url
        self.login = login
        self.password = password
        if self.login is None or self.password is None:
            raise WebDavException(400, "Please, specify login and password for WebDav account.")

    def _sendRequest(self, type, add_url="/", add_headers=None, data=None):
        headers = {"Accept": "*/*"}
        if add_headers:
            headers.update(add_headers)
        url = self.url + add_url
        return request(type, url, headers=headers, auth=(self.login, self.password), data=data, timeout=5)

    def get_response(self, path):
        resp = self._sendRequest("GET", path)
        if resp.status_code == 200:
            return resp
        else:
            raise WebDavException(resp.status_code, resp.content)

    def exists(self, path):
        resp = self._sendRequest("HEAD", path)
        if resp.status_code == 200:
            return True
        else:
            return False

    def delete(self, path):
        resp = self._sendRequest("DELETE", path)
        if resp.status_code == 204:
            return resp
        else:
            raise WebDavException(resp.status_code, resp.content)

    def upload(self, file, path):
        """Upload file."""

        if self.exists(path):
            logger.debug('WebDav file `%s` exists, overwriting', path)
            self.delete(path)

        data = ProgressNotifier(file)
        resp = self._sendRequest("PUT", path, data=data)

        if resp.status_code != 201:
            raise WebDavException(resp.status_code, resp.content)
