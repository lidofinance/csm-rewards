import json
import sys
from typing import TypedDict

from wake.deployment import Abi, Address, chain, print

from env import EnvNotSet, getenv
from ipfs import GW3, PublicIPFS
from pytypes.contracts.ICSFeeDistributor import ICSFeeDistributor
from tree import CSMRewardTree

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

SECONDS_PER_SLOT = 12
SECONDS_PER_DAY = 3600 * 24
EVENTS_RANGE_BLOCKS = SECONDS_PER_DAY * 45 // SECONDS_PER_SLOT


class Log(TypedDict):
    transactionHash: str
    blockNumber: str


@chain.connect(getenv("RPC_URL"))
def main():
    distributor = ICSFeeDistributor(getenv("DISTRIBUTOR_ADDRESS"))
    chain.default_call_account = Address(0)

    last_net_bn = chain.blocks["latest"].number

    curr_root = distributor.treeRoot(block=last_net_bn)
    curr_cid = distributor.treeCid(block=last_net_bn)

    if not curr_cid or not curr_root:
        print("No distribution happened so far")
        sys.exit(EXIT_SUCCESS)

    logs: list[Log] = chain.chain_interface.get_logs(
        from_block=last_net_bn - EVENTS_RANGE_BLOCKS,
        to_block=last_net_bn,
        topics=[f"0x{ICSFeeDistributor.DistributionDataUpdated.selector.hex()}"],
        address=getenv("DISTRIBUTOR_ADDRESS"),
    )

    distributed, last_upd_bn = 0, None

    for evt in reversed(logs):
        tx = chain.txs[evt["transactionHash"]]
        # @see https://github.com/lidofinance/community-staking-module/blob/cd11a7964e6054a3f8b9a4ea82ce37044d408b04/src/CSFeeOracle.sol#L116
        try:
            decoded = Abi.decode(
                (
                    f"({
                    ",".join([
                        "uint256",  # consensusVersion
                        "uint256",  # refSlot
                        "bytes32",  # treeRoot
                        "string",  # treeCid
                        "string",  # logCid
                        "uint256",  # distributed
                    ])})",
                    "uint256",  # contractVersion
                ),
                tx.data[4:],
            )
        except Exception:
            # NOTE: We changed the method's signature at some point.
            pass
        else:
            ((_, _, root, _, _, distributed), _) = decoded
            if root == curr_root:
                print(f"Latest distribution happened at tx {tx.tx_hash}, {distributed=}, root=0x{root.hex()}")
                last_upd_bn = int(evt["blockNumber"], 16)
                break

    if not last_upd_bn:
        eprint("No distribution event found")
        sys.exit(EXIT_FAILURE)

    try:
        ipfs = GW3(
            getenv("GW3_ACCESS_KEY"),
            getenv("GW3_SECRET_KEY"),
        )
    except EnvNotSet:
        ipfs = PublicIPFS()

    curr_tree = CSMRewardTree.load(json.loads(ipfs.fetch(curr_cid)))
    if curr_tree.root != curr_root:
        eprint(f"Unexpected current tree root: actual={curr_tree.root}, expected={curr_root}")
        sys.exit(EXIT_FAILURE)

    prev_cid = distributor.treeCid(block=last_upd_bn - 1)
    prev_tree = None
    if prev_cid:
        prev_root = distributor.treeRoot(block=last_upd_bn - 1)
        prev_tree = CSMRewardTree.load(json.loads(ipfs.fetch(prev_cid)))
        if prev_tree.root != prev_root:
            eprint(f"Unexpected previous tree root: actual={prev_tree.root}, expected={prev_root}")
            sys.exit(EXIT_FAILURE)

    diff = curr_tree.total_shares - prev_tree.total_shares if prev_tree else curr_tree.total_shares
    if diff != distributed:
        eprint(f"Unexpected distribution results: actual={diff}, expected={distributed}")
        sys.exit(EXIT_FAILURE)

    if prev_tree:
        is_failed = False

        for no_id, prev_shares in prev_tree:
            if no_id not in curr_tree.kv:
                eprint(f"NO with id {no_id} has gone from the distribution in the tree with root 0x{curr_root.hex()}")
                is_failed = True

            if curr_tree.kv[no_id] < prev_shares:
                eprint(f"Shares of NO with id {no_id} decreased in the tree with root 0x{curr_root.hex()}")
                is_failed = True

        if is_failed:
            sys.exit(EXIT_FAILURE)

    print("All checks passed!")


def eprint(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
