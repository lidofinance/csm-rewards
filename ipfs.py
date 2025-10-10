import requests


class PublicIPFS:
    """Public IPFS gateway"""

    GATEWAY = "https://ipfs.io"

    def __init__(self, *, timeout: int = 120) -> None:
        super().__init__()
        self.timeout = timeout

    def fetch(self, cid: str) -> bytes:
        url = f"{self.GATEWAY}/ipfs/{cid}"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content
