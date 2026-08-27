import os

import requests


class PublicIPFS:
    """Public IPFS gateway"""

    GATEWAY: str

    def __init__(self, *, timeout: int = 120) -> None:
        super().__init__()
        self.timeout = timeout
        self.GATEWAY = os.getenv("IPFS_GATEWAY") or "https://ipfs.io"

    def fetch(self, cid: str) -> bytes:
        url = f"{self.GATEWAY}/ipfs/{cid}"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content
