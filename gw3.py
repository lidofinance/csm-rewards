import base64
import hashlib
import hmac
import time
from urllib.parse import urlencode, urlparse

import requests


class GW3:
    """gw3.io client"""

    ENDPOINT = "https://gw3.io"

    def __init__(self, access_key: str, access_secret: str, *, timeout: int = 120) -> None:
        self.access_key = access_key
        self.access_secret = base64.urlsafe_b64decode(access_secret)
        self.timeout = timeout

    def fetch(self, cid: str):
        resp = self._send("GET", f"{self.ENDPOINT}/ipfs/{cid}")
        return resp.content

    def _auth_upload(self, size: int) -> str:
        response = self._send("POST", f"{self.ENDPOINT}/ipfs/", {"size": size})
        return response.json()["data"]["url"]

    def _send(self, method: str, url: str, params: dict | None = None) -> requests.Response:
        req = self._signed_req(method, url, params)
        response = requests.Session().send(req, timeout=self.timeout)
        response.raise_for_status()
        return response

    def _signed_req(self, method: str, url: str, params: dict | None = None) -> requests.PreparedRequest:
        params = params or {}
        params["ts"] = str(int(time.time()))
        query = urlencode(params, doseq=True)

        parsed_url = urlparse(url)
        data = "\n".join((method, parsed_url.path, query)).encode("utf-8")
        mac = hmac.new(self.access_secret, data, hashlib.sha256)
        sign = base64.urlsafe_b64encode(mac.digest())

        req = requests.Request(method=method, url=url, params=params)
        req.headers["X-Access-Key"] = self.access_key
        req.headers["X-Access-Signature"] = sign.decode("utf-8")
        return req.prepare()
