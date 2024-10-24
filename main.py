import json
import subprocess
import sys

from wake.deployment import Address, chain, print

from env import EnvNotSet, getenv
from ipfs import GW3, PublicIPFS
from pytypes.contracts.ICSFeeDistributor import ICSFeeDistributor
from tree import CSMRewardTree

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


@chain.connect(getenv("RPC_URL"))
def main():
    distributor = ICSFeeDistributor(getenv("DISTRIBUTOR_ADDRESS"))
    chain.default_call_account = Address(0)

    root = distributor.treeRoot()
    cid = distributor.treeCid()

    print(f"root={root.hex()} {cid=}")

    if not cid:
        print("No tree CID stored so far")
        sys.exit(EXIT_SUCCESS)

    try:
        ipfs = GW3(
            getenv("GW3_ACCESS_KEY"),
            getenv("GW3_SECRET_KEY"),
        )
    except EnvNotSet:
        ipfs = PublicIPFS()

    tree = CSMRewardTree.load(json.loads(ipfs.fetch(cid)))
    if tree.root != root:
        print(f"tree.root={tree.root.hex()}")
        print("error: Roots mismatch")
        sys.exit(EXIT_FAILURE)

    dump = tree.dump()

    with open("tree.json", "w", encoding="utf-8") as fp:
        json.dump(dump, fp, indent=2, default=default)

    proofs = {
        f"CSM Operator {v["value"][0]}": {
            "cumulativeFeeShares": v["value"][1],
            "proof": list(tree.get_proof(v["treeIndex"])),
        }
        for v in dump["values"]
    }

    with open("proofs.json", "w", encoding="utf-8") as fp:
        json.dump(proofs, fp, indent=2, default=default)

    # XXX: CI-only stuff below.

    try:
        github_output = getenv("GITHUB_OUTPUT")
    except EnvNotSet:
        sys.exit(EXIT_SUCCESS)

    git_diff = subprocess.run(["git", "diff", "--exit-code", "--quiet", "tree.json"])

    with open(github_output, "a", encoding="utf-8") as fp:
        fp.write(
            "\n".join(
                [
                    "",
                    f"cid={cid}",
                    f"updated={git_diff.returncode != 0}",
                ]
            )
        )


def default(o):
    if isinstance(o, bytes):
        return f"0x{o.hex()}"
    raise ValueError(f"Unexpected type for json encoding, got {repr(o)}")
