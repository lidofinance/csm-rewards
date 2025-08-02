import json
import math
import sys
from collections import defaultdict
from typing import TypedDict

from wake.deployment import Abi, Address, TransactionAbc, bytes32, chain, print

from env import getenv
from ipfs import PublicIPFS
from pytypes.contracts.ICSFeeDistributor import ICSFeeDistributor
from tree import CSMRewardTree

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

SECONDS_PER_SLOT = 12
SECONDS_PER_DAY = 3600 * 24
EVENTS_RANGE_BLOCKS = SECONDS_PER_DAY * 45 // SECONDS_PER_SLOT
BATCH_SIZE = 10_000


class Log(TypedDict):
    transactionHash: str
    blockNumber: str


@chain.connect(getenv("RPC_URL"))
def main():
    distributor = ICSFeeDistributor(getenv("DISTRIBUTOR_ADDRESS"))
    chain.default_call_account = Address(0)

    last_net_bn = chain.blocks["latest"].number

    curr_root = distributor.treeRoot(block=last_net_bn, type=1, gas_price=0)
    curr_cid = distributor.treeCid(block=last_net_bn, type=1, gas_price=0)

    if not curr_cid or not curr_root:
        print("No distribution happened so far")
        sys.exit(EXIT_SUCCESS)

    events: list[Log] = []
    from_block = max(last_net_bn - EVENTS_RANGE_BLOCKS, 0)
    while from_block <= last_net_bn:
        events.extend(
            chain.chain_interface.get_logs(
                from_block=from_block,
                to_block=min(from_block + BATCH_SIZE, last_net_bn),
                topics=[f"0x{ICSFeeDistributor.DistributionDataUpdated.selector.hex()}"],
                address=getenv("DISTRIBUTOR_ADDRESS"),
            )
        )
        from_block += BATCH_SIZE + 1

    distributed = 0
    ref_slot: int | None = None
    tx: TransactionAbc | None = None

    for evt in reversed(events):
        tx = chain.txs[evt["transactionHash"]]

        # Try to decode CSM v1 transaction input.
        # @see https://github.com/lidofinance/community-staking-module/blob/cd11a7964e6054a3f8b9a4ea82ce37044d408b04/src/CSFeeOracle.sol#L116
        try:
            decoded = Abi.decode(
                (
                    f"({
                        ','.join(
                            [
                                'uint256',  # consensusVersion
                                'uint256',  # refSlot
                                'bytes32',  # treeRoot
                                'string',  # treeCid
                                'string',  # logCid
                                'uint256',  # distributed
                            ]
                        )
                    })",
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
                    f"Latest distribution happened at tx {tx.tx_hash},{distributed=}, root=0x{root.hex()}, {ref_slot=}"
                )
                break

        # Try to decode CSM v2 transaction input.
        # NOTE: The block will be replaced with distribution data history getter eventually.
        # @see https://github.com/lidofinance/community-staking-module/blob/40ecb6d9c1934ec29ef88f7b42164dd38a73d717/src/CSFeeOracle.sol#L103
        try:
            decoded = Abi.decode(
                (
                    f"({
                        ','.join(
                            [
                                'uint256',  # consensusVersion
                                'uint256',  # refSlot
                                'bytes32',  # treeRoot
                                'string',  # treeCid
                                'string',  # logCid
                                'uint256',  # distributed
                                'uint256',  # rebate
                                'bytes32',  # strikesTreeRoot
                                'string',  # strikesTreeCid
                            ]
                        )
                    })",
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
                    f"Latest distribution happened at tx {tx.tx_hash},{distributed=}, root=0x{root.hex()}, {ref_slot=}"
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

    prev_root = distributor.treeRoot(block=tx.block_number - 1, type=1, gas_price=0)
    prev_cid = distributor.treeCid(block=tx.block_number - 1, type=1, gas_price=0)

    prev_tree = None
    if prev_cid:
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

    log_cid = distributor.logCid(block=last_net_bn, type=1, gas_price=0)
    logs = json.loads(ipfs.fetch(log_cid))
    print(f"[OK] Latest frame log(s) restored from CID={log_cid}")

    mr_frame_log = logs if type(logs) is dict else logs[-1]
    assert type(mr_frame_log) is dict

    if (log_ref_slot := mr_frame_log["blockstamp"]["ref_slot"]) != ref_slot:
        eprint(f"Invalid ref_slot in log, got={log_ref_slot} expected={ref_slot}")
        sys.exit(EXIT_FAILURE)

    log_blockstamp = mr_frame_log["blockstamp"]
    report_block = chain.blocks[log_blockstamp["block_number"]]

    if (log_block_hash := log_blockstamp["block_hash"]) != report_block.hash:
        eprint(
            f"Invalid block in log, got hash {report_block.hash} by {report_block.number}, expected={log_block_hash}"
        )
        sys.exit(EXIT_FAILURE)

    if report_block.number > tx.block_number:
        eprint(f"Invalid block in log, got={report_block.number} for tx within block={tx.block_number}")
        sys.exit(EXIT_FAILURE)

    print("[OK] Report blockstamp seems to be valid")

    rebate_recipient = chain.chain_interface.get_storage_at(
        str(distributor.address),
        0x07,
        report_block.hash,
    )
    csm_v2 = rebate_recipient != bytes32(0)
    print(f"[OK] Detected CSM version is v{2 if csm_v2 else 1}")

    if csm_v2:
        assert type(logs) is list
        total_rewards_per_op = defaultdict[int, int](int)

        for log in logs:
            shares_of_op = defaultdict[int, int](int)
            total_shares = 0

            for op_id, op in log["operators"].items():
                for v in op["validators"].values():
                    if v["slashed"]:
                        continue
                    if v["performance"] > v["threshold"]:
                        op_share = math.ceil(v["attestation_duty"]["assigned"] * v["rewards_share"])
                        total_shares += v["attestation_duty"]["assigned"]
                        shares_of_op[int(op_id)] += op_share

            total_rewards_in_frame = 0
            for op_id, op in log["operators"].items():
                op_reward = log["distributable"] * shares_of_op[int(op_id)] // total_shares
                total_rewards_per_op[int(op_id)] += op_reward
                total_rewards_in_frame += op_reward
                if op["distributed_rewards"] != op_reward:
                    eprint(
                        f"Rewards of NO with id {op_id} are not correct: got {op['distributed_rewards']}, expected {op_reward}"
                    )
                    is_failed = True

            rebate = log["distributable"] - total_rewards_in_frame if total_rewards_in_frame else 0
            if log["rebate_to_protocol"] != rebate:
                eprint(f"Unexpected rebate amount, got {log['rebate_to_protocol']}, expected {rebate}")
                is_failed = True

        for op_id, rewards_in_logs in total_rewards_per_op.items():
            if not rewards_in_logs:
                continue
            rewards_in_tree = curr_tree.kv[op_id]
            if prev_tree and op_id in prev_tree.kv:
                rewards_in_tree -= prev_tree.kv[op_id]
            diff = rewards_in_tree - rewards_in_logs
            if diff != 0:
                eprint(
                    f"Shares of NO with id {op_id} by frame logs are not consistent with the value in the tree"
                    + f"\n\t{rewards_in_tree=} != {rewards_in_logs=}, {diff=}"
                )
                is_failed = True
    else:
        assert type(logs) is dict
        shares_of_op = defaultdict[int, int](int)
        for op_id, op in logs["operators"].items():
            for v in op["validators"].values():
                if v["slashed"]:
                    continue
                perf = v["perf"]["included"] / v["perf"]["assigned"]
                if perf > logs["threshold"]:
                    shares_of_op[int(op_id)] += v["perf"]["assigned"]

        total_shares = sum(shares_of_op.values())
        for op_id, op_share in shares_of_op.items():
            expected = logs["distributable"] * op_share // total_shares
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

    print("[OK] Tree distribution is consistent with the frame log(s)")
    print("[OK] All checks passed!")


def eprint(msg: str) -> None:
    print(f"[FAIL]: {msg}", file=sys.stderr)
