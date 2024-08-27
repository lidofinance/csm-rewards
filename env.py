import os

from dotenv import load_dotenv

load_dotenv()


class EnvNotSet(Exception): ...


def getenv(name: str) -> str:
    if name not in os.environ:
        raise EnvNotSet(f"Variable {name=} is not set")
    return os.environ[name]
