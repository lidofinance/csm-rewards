import json
import math
import sys
import time
from collections import defaultdict
from enum import Enum, auto
from functools import wraps
from typing import Callable

from wake.deployment import Address, chain, print
from wake.development.chain_interfaces import JsonRpcCommunicator

from env import getenv
from ipfs import PublicIPFS
from pytypes.contracts.IFeeDistributor import IFeeDistributor
from tree import CSMRewardTree

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


class LogFormat(Enum):
    V2 = auto()
    V3 = auto()


@chain.connect(getenv("RPC_URL"))
def main():
    distributor = IFeeDistributor(getenv("DISTRIBUTOR_ADDRESS"))
    chain.default_call_account = Address(0)

    last_net_bn = chain.blocks["latest"].number

    # type=1 + gas_price=0 makes the eth_call a legacy tx with no gas requirement, which keeps
    # strict RPC nodes from rejecting calls made from address(0) on a balance/gas check.
    curr_root = distributor.treeRoot(block=last_net_bn, type=1, gas_price=0)
    curr_cid = distributor.treeCid(block=last_net_bn, type=1, gas_price=0)

    if not curr_cid or not curr_root:
        print("No distribution happened so far")
        sys.exit(EXIT_SUCCESS)

    history_count = distributor.distributionDataHistoryCount(block=last_net_bn, type=1, gas_price=0)
    if history_count == 0:
        eprint("No distribution history found")
        sys.exit(EXIT_FAILURE)

    latest_entry = distributor.getHistoricalDistributionData(history_count - 1, block=last_net_bn, type=1, gas_price=0)
    if latest_entry.treeRoot != curr_root or latest_entry.treeCid != curr_cid:
        eprint(
            "Latest distribution history entry does not match the current tree"
            + f"\n\tactual=root 0x{latest_entry.treeRoot.hex()} CID={latest_entry.treeCid}"
            + f"\n\texpected=root 0x{curr_root.hex()} CID={curr_cid}"
        )
        sys.exit(EXIT_FAILURE)

    ref_slot = latest_entry.refSlot
    distributed = latest_entry.distributed
    rebate = latest_entry.rebate
    log_cid = latest_entry.logCid

    prev_root = None
    prev_cid = ""
    if history_count > 1:
        prev_entry = distributor.getHistoricalDistributionData(history_count - 2, block=last_net_bn, type=1, gas_price=0)
        prev_root = prev_entry.treeRoot
        prev_cid = prev_entry.treeCid

    print(
        f"Latest distribution: distributed={format_shares(distributed)}, "
        f"rebate={format_shares(rebate)}, root=0x{curr_root.hex()}, {ref_slot=}"
    )

    ipfs = PublicIPFS()

    curr_tree = CSMRewardTree.load(json.loads(ipfs.fetch(curr_cid)))
    if curr_tree.root != curr_root:
        eprint(f"Unexpected current tree root: actual={curr_tree.root}, expected={curr_root}")
        sys.exit(EXIT_FAILURE)
    print(f"[OK] CID={curr_cid} contains a tree with an expected root")

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

    logs = json.loads(ipfs.fetch(log_cid))
    print(f"[OK] Latest frame log(s) restored from CID={log_cid}")

    # Supported log shapes:
    #   - current CSM module: a list of frame dicts.
    #   - next CSM module:    a dict {"_ver": N, "frames": [...]} wrapping the list.
    if isinstance(logs, dict) and "frames" in logs:
        log_frames = logs["frames"]
        log_format = LogFormat.V3
    elif isinstance(logs, list):
        log_frames = logs
        log_format = LogFormat.V2
    else:
        eprint(f"Unexpected frame log format: {type(logs).__name__}")
        sys.exit(EXIT_FAILURE)

    if not log_frames or not all(isinstance(log, dict) for log in log_frames):
        eprint("Unexpected frame log format: expected non-empty frame dict(s)")
        sys.exit(EXIT_FAILURE)

    mr_frame_log = log_frames[-1]

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

    print("[OK] Report blockstamp seems to be valid")

    total_rewards_per_op = defaultdict[int, int](int)

    for log in log_frames:
        shares_of_op = defaultdict[int, int](int)
        total_shares = 0

        val_idx_to_op: dict[int, int] = {}
        for op_id, op in log["operators"].items():
            for i, v in op["validators"].items():
                if i in val_idx_to_op:
                    eprint(f"Found second entry for validator {i}: {op_id} and {val_idx_to_op[i]}")
                    is_failed = True
                val_idx_to_op[i] = op_id

                if v["slashed"]:
                    continue

                if log_format is LogFormat.V3:
                    reward_share = v["reward_share"]
                    multiplier = v["participation_share_multiplier"]
                    above_threshold = v["performance"] >= v["threshold"]
                else:
                    reward_share = v["rewards_share"]
                    multiplier = 1
                    above_threshold = v["performance"] > v["threshold"]

                if above_threshold:
                    assigned_att = v["attestation_duty"]["assigned"] * multiplier
                    op_share = math.ceil(assigned_att * reward_share)
                    total_shares += assigned_att
                    shares_of_op[int(op_id)] += op_share

        total_rewards_in_frame = 0
        for op_id, op in log["operators"].items():
            op_reward = log["distributable"] * shares_of_op[int(op_id)] // total_shares if total_shares else 0
            total_rewards_per_op[int(op_id)] += op_reward
            total_rewards_in_frame += op_reward
            if op["distributed_rewards"] != op_reward:
                eprint(
                    f"Rewards of NO with id {op_id} are not correct: "
                    f"got {op['distributed_rewards']}, expected {op_reward}"
                )
                is_failed = True

        if log_format is LogFormat.V3:
            rebate = log["distributable"] - total_rewards_in_frame
        else:
            rebate = log["distributable"] - total_rewards_in_frame if total_rewards_in_frame else 0
        if log["rebate_to_protocol"] != rebate:
            eprint(f"Unexpected rebate amount, got {log['rebate_to_protocol']}, expected {rebate}")
            is_failed = True

    for op_id, rewards_in_logs in total_rewards_per_op.items():
        if not rewards_in_logs:
            continue
        rewards_in_tree = curr_tree.kv.get(op_id, 0)
        if prev_tree and op_id in prev_tree.kv:
            rewards_in_tree -= prev_tree.kv[op_id]
        diff = rewards_in_tree - rewards_in_logs
        if diff != 0:
            eprint(
                f"Shares of NO with id {op_id} by frame logs are not consistent with the value in the tree"
                + f"\n\t{rewards_in_tree=} != {rewards_in_logs=}, {diff=}"
            )
            is_failed = True

    if is_failed:
        sys.exit(EXIT_FAILURE)

    print("[OK] Tree distribution is consistent with the frame log(s)")
    print("[OK] All checks passed!")


def eprint(msg: str) -> None:
    print(f"[FAIL]: {msg}", file=sys.stderr)


def format_shares(value: int) -> str:
    if value <= 10**18:
        return str(value)

    whole, fraction = divmod(value, 10**18)
    if fraction == 0:
        scaled = str(whole)
    else:
        scaled = f"{whole}.{str(fraction).zfill(18)[:2].rstrip('0')}"
    return f"{value} ({scaled} x 1e18)"


def with_retry(func: Callable) -> Callable:
    MAX_RETRIES = 3
    DELAY_S = 1

    @wraps(func)
    def wrapped(*args, **kwargs):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(DELAY_S)

    return wrapped


# chain.chain_interface uses the class under the hood
# with_retry decorator will retry a few specific requests such as `evm_snapshot` during a chain detection phase
JsonRpcCommunicator.send_request = with_retry(JsonRpcCommunicator.send_request)
