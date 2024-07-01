import json
import os
import subprocess
import sys

from wake.deployment import Address, default_chain, print

from gw3 import GW3
from pytypes.contracts.ICSFeeDistributor import ICSFeeDistributor
from tree import StandardMerkleTree

type NodeOperatorID = int
type Shares = int


@default_chain.connect(os.environ["RPC_URL"])
def main():
    ipfs = GW3(os.environ["GW3_ACCESS_KEY"], os.environ["GW3_SECRET_KEY"])
    distributor = ICSFeeDistributor(os.environ["DISTRIBUTOR_ADDRESS"])
    root = distributor.treeRoot(from_=Address(0))
    cid = distributor.treeCid(from_=Address(0))
    print(f"root={root.hex()} {cid=}")

    if not cid:
        print("No CID stored so far")
        sys.exit()

    tree = StandardMerkleTree[tuple[NodeOperatorID, Shares]].load(json.loads(ipfs.fetch(cid)))
    if tree.root != root:
        print(f"tree.root={tree.root.hex()}")
        print("Roots mismatch")
        sys.exit(1)

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

    github_output = os.getenv("GITHUB_OUTPUT", None)
    if not github_output:
        return

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
