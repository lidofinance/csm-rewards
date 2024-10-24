from abc import ABC, abstractmethod
from functools import cached_property, reduce
from typing import Collection, Generic, Iterable, Self, Sequence, TypedDict, TypeVar

from eth_abi.abi import encode
from eth_hash.auto import keccak
from eth_typing import TypeStr


class MerkleTree(ABC):
    """Merkle Tree interface"""

    @property
    @abstractmethod
    def root(self) -> bytes: ...

    @abstractmethod
    def find(self, leaf: bytes) -> int: ...

    @abstractmethod
    def get_proof(self, index: int) -> Iterable[bytes]: ...

    @classmethod
    @abstractmethod
    def verify(cls, root: bytes, leaf: bytes, proof: Iterable[bytes]) -> bool: ...

    @classmethod
    @abstractmethod
    def __hash_leaf__(cls, leaf: bytes) -> bytes: ...

    @classmethod
    @abstractmethod
    def __hash_node__(cls, lhs: bytes, rhs: bytes) -> bytes: ...


class CompleteBinaryMerkleTree(MerkleTree):
    """The tree shaped as a [complete binary tree](https://xlinux.nist.gov/dads/HTML/completeBinaryTree.html)."""

    tree: tuple[bytes, ...]

    def __init__(self, leaves: Collection[bytes]):
        if not leaves:
            raise ValueError("Attempt to create an empty tree")

        tree = [b""] * (2 * len(leaves) - 1)

        for i, leaf in enumerate(leaves):
            tree[len(tree) - 1 - i] = leaf

        for i in range(len(tree) - 1 - len(leaves), -1, -1):
            tree[i] = self.__hash_node__(tree[2 * i + 1], tree[2 * i + 2])

        self.tree = tuple(tree)

    @property
    def root(self) -> bytes:
        return self.tree[0]

    def find(self, leaf: bytes) -> int:
        try:
            return self.tree.index(leaf)
        except ValueError as e:
            raise ValueError("Node not found") from e

    def get_proof(self, index: int) -> Iterable[bytes]:
        i = index
        while i > 0:
            yield self.tree[i - (-1) ** (i % 2)]
            i = (i - 1) // 2

    @classmethod
    def verify(cls, root: bytes, leaf: bytes, proof: Iterable[bytes]) -> bool:
        return reduce(lambda a, b: cls.__hash_node__(a, b), proof, leaf) == root


T = TypeVar("T", bound=Iterable)


class Value(Generic[T], TypedDict):
    value: T
    treeIndex: int


class Dump(Generic[T], TypedDict):
    format: str
    leafEncoding: Iterable[TypeStr]
    tree: Collection[bytes]
    values: Sequence[Value[T]]


class StandardMerkleTree(Generic[T], CompleteBinaryMerkleTree):
    """
    OpenZeppelin Standard Merkle Tree

    - The tree is shaped as a complete binary tree.
    - The leaves are sorted.
    - The leaves are the result of ABI encoding a series of values.
    - The hash used is Keccak256.
    - The leaves are double-hashed to prevent second preimage attacks.
    """

    encoding: Iterable[TypeStr]
    values: Sequence[Value[T]]

    FORMAT = "standard-v1"

    def __init__(self, values: Sequence[T], encoding: Iterable[TypeStr]):
        self.encoding = encoding

        leaves = tuple(sorted(self.leaf(v) for v in values))
        super().__init__(leaves)

        self.values = tuple({"value": v, "treeIndex": self.find(self.leaf(v))} for v in values)

    def leaf(self, value: T) -> bytes:
        return self.__hash_leaf__(encode(self.encoding, value))

    def dump(self) -> Dump[T]:
        return {
            "format": self.FORMAT,
            "leafEncoding": self.encoding,
            "tree": self.tree,
            "values": self.values,
        }

    @classmethod
    def load(cls, data: Dump[T]) -> Self:
        if "format" not in data or data["format"] != cls.FORMAT:
            raise ValueError("Unexpected dump format value")
        if "leafEncoding" not in data:
            raise ValueError("No leaf encoding provided")
        if "values" not in data:
            raise ValueError("No values provided")
        return cls([e["value"] for e in data["values"]], data["leafEncoding"])

    @classmethod
    def __hash_leaf__(cls, leaf: bytes) -> bytes:
        return keccak(keccak(leaf))

    @classmethod
    def __hash_node__(cls, lhs: bytes, rhs: bytes) -> bytes:
        if lhs > rhs:
            lhs, rhs = rhs, lhs
        return keccak(lhs + rhs)


type NodeOperatorID = int
type Shares = int


class CSMRewardTree(StandardMerkleTree[tuple[NodeOperatorID, Shares]]):
    kv: dict[NodeOperatorID, Shares]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kv = {no_id: shares for (no_id, shares) in self}

    @cached_property
    def total_shares(self) -> Shares:
        return sum(shares for (_, shares) in self)

    def __iter__(self):
        return (v["value"] for v in self.values)
