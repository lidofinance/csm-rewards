import json
import sys
from collections import defaultdict
from typing import TypedDict

from wake.deployment import Abi, Address, TransactionAbc, chain, print

from env import getenv
from ipfs import PublicIPFS
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
        from_block=max(last_net_bn - EVENTS_RANGE_BLOCKS, 0),
        to_block=last_net_bn,
        topics=[f"0x{ICSFeeDistributor.DistributionDataUpdated.selector.hex()}"],
        address=getenv("DISTRIBUTOR_ADDRESS"),
    )

    distributed = 0
    ref_slot: int | None = None
    tx: TransactionAbc | None = None

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
            ((_, ref_slot, root, _, _, distributed), _) = decoded
            if root == curr_root:
                print(
                    f"Latest distribution happened at tx {tx.tx_hash},"
                    f"{distributed=}, root=0x{root.hex()}, {ref_slot=}"
                )
                break

    if not tx:
        eprint("No distribution event found")
        sys.exit(EXIT_FAILURE)

    if not ref_slot:
        eprint("Unable to get reference slot from the report tx")
        sys.exit(EXIT_FAILURE)

    ipfs = PublicIPFS()

    curr_tree = CSMRewardTree.load(json.loads(ipfs.fetch(curr_cid)))
    if curr_tree.root != curr_root:
        eprint(f"Unexpected current tree root: actual={curr_tree.root}, expected={curr_root}")
        sys.exit(EXIT_FAILURE)
    print(f"[OK] CID={curr_cid} contains a tree with an expected root")

    prev_cid = distributor.treeCid(block=tx.block_number - 1)
    prev_tree = None
    if prev_cid:
        prev_root = distributor.treeRoot(block=tx.block_number - 1)
        prev_tree = CSMRewardTree.load(json.loads(ipfs.fetch(prev_cid)))
        if prev_tree.root != prev_root:
            eprint(f"Unexpected previous tree root: actual={prev_tree.root}, expected={prev_root}")
            sys.exit(EXIT_FAILURE)
        print(f"[OK] Previous distribution tree found via CID={prev_cid}")

    diff = curr_tree.total_shares - prev_tree.total_shares if prev_tree else curr_tree.total_shares
    if diff != distributed:
        eprint(f"Unexpected distribution results: actual={diff}, expected={distributed}")
        sys.exit(EXIT_FAILURE)
    print("[OK] Total amount of shares distributed via the latest tree is correct")

    is_failed = False

    if prev_tree:
        for no_id, prev_shares in prev_tree:
            if no_id not in curr_tree.kv:
                eprint(f"NO with id {no_id} has gone from the distribution in the tree with root 0x{curr_root.hex()}")
                is_failed = True

            if curr_tree.kv[no_id] < prev_shares:
                eprint(f"Shares of NO with id {no_id} decreased in the tree with root 0x{curr_root.hex()}")
                is_failed = True

    if is_failed:
        sys.exit(EXIT_FAILURE)

    log_cid = distributor.logCid(block=last_net_bn)
    log = json.loads(ipfs.fetch(log_cid))
    print(f"[OK] Latest frame log restored from CID={log_cid}")

    if (log_ref_slot := log["blockstamp"]["ref_slot"]) != ref_slot:
        eprint(f"Invalid ref_slot in log, got={log_ref_slot} expected={ref_slot}")
        sys.exit(EXIT_FAILURE)

    report_block = chain.blocks[log["blockstamp"]["block_number"]]

    if (log_block_hash := log["blockstamp"]["block_hash"]) != report_block.hash:
        eprint(
            f"Invalid block in log, got hash {report_block.hash} by {report_block.number}, "
            f"expected={log_block_hash}"
        )
        sys.exit(EXIT_FAILURE)

    if report_block.number > tx.block_number:
        eprint(f"Invalid block in log, got={report_block.number} for tx within block={tx.block_number}")
        sys.exit(EXIT_FAILURE)

    print("[OK] Report blockstamp seems to be valid")

    shares_of_op = defaultdict[int, int](int)
    for op_id, op in log["operators"].items():
        for v in op["validators"].values():
            if v["slashed"]:
                continue
            perf = v["perf"]["included"] / v["perf"]["assigned"]
            if not v["slashed"] and perf > log["threshold"]:
                shares_of_op[int(op_id)] += v["perf"]["assigned"]

    total_shares = sum(shares_of_op.values())
    for op_id, op_share in shares_of_op.items():
        expected = log["distributable"] * op_share // total_shares
        actual = curr_tree.kv[op_id]
        if prev_tree and op_id in prev_tree.kv:
            actual -= prev_tree.kv[op_id]
        diff = actual - expected
        if diff != 0:
            eprint(
                f"Shares of NO with id {op_id} by frame log are not consistent with the value in the tree"
                + f"\n\t{actual}[tree] != {expected}[log], {diff=}"
            )
            is_failed = True

    if is_failed:
        sys.exit(EXIT_FAILURE)
    print("[OK] Tree distribution is consistent with the frame log")

    print("[OK] All checks passed!")


def eprint(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
