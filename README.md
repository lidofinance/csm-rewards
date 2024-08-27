If you're a Node Operator in CSM, you get staking rewards as a part of Lido
protocol fees. The allocation of rewards for CSM operators using a Merkle tree
is provided by CSM Performance Oracle once in a frame, making a new portion of
the rewards available for claim.

Here you can find the latest [rewards tree](./tree.json). Most of the time you
won't need it, because [CSM UI](https://csm.testnet.fi) will fetch the latest
data under the hood, and you will able to claim your rewards right in place. In
the case of UI unavailabilty you will be able to claim rewards manually using
the pre-generated [proofs](./proofs.json).

---

Claim rewards using Etherscan

- Open [proofs.json](./proofs.json) and locate your record, e.g. 'CSM Operator 42'
- Open CSM contract on Etherscan and go to 'Contact' -> 'Write as Proxy' tab
  ([direct
  link](https://holesky.etherscan.io/address/0x4562c3e63c2e586cD1651B958C22F88135aCAd4f#writeProxyContract))
- Connect your wallet to Etherscan
- Select `claim*` method you want to use, e.g. `claimRewardsStETH`.
- Enter your Node Operator ID, e.g. `42`.
- Enter the amout you wish to claim in the token of choice or use any large
  value, e.g
  `115792089237316195423570985008687907853269984665640564039457584007913129639935`
  if you don't know the exact number.
- Copy and paste the `cumulativeFeeShares` from the proof record.
- Copy `proof` value from the proof record, remove
    - square brackets
    - quotes
    - spaces
    - new lines

  , and paste it to the `rewardsProof` input field, e.g:
    ```js
    "proof": [
      "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    ] =>
    0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    ```
- Click 'Write' button and sign a transaction.

---

The primary intent of this repository is to act as a backup for the rewards trees stored
in the IPFS network. By design the latest tree is the only one required to claim rewards
from CSM. That's why the repository tracks only the latest tree, even though the
previous versions can be restored by traversing git history.

Here's a simple [script](./main.py) used to retrieve the IPFS content identifier
(CID) of the latest tree from the CSM distributor contract, fetch the tree
itself from the IPFS network, and write down the artifacts: a
[tree](./tree.json) and generated [proofs](./proofs.json). Currently the script
is executed automatically every hour via GitHub actions, and the latest
artifacts are committed back to the repository.

---

To run the script manually follow the instructions below:

1. Make sure you have installed `python >= 3.12` and `poetry >= 1.8.3`.

1. Install python dependencies:

    ```shell
    poetry install
    ```

1. Generate stubs for interaction with contracts:

    ```shell
    poetry run wake up pytypes
    ```

1. Copy `.env.example` to `.env`

    ```shell
    cp .env.example .env
    ```

1. Run the script:

    ```shell
    poetry run wake run main.py
    ```

> [!NOTE]
> Public Ethereun RPC and IPFS endpoints may be non-reliable, so consider using
> private/paid endpoints instead.

A free [gw3.io](https://www.gw3.io) plan can be used for IPFS:

- Go to [Login](https://www.gw3.io/login) page
- Sign in or create a new account
- Go to [API keys](https://www.gw3.io/apis) page
- Press **Generate API key** button
- Fill in the "Name" field, e.g. with "CSM"
- Select the following permissions:
   - Read
- Press **Create** button
- Copy **Access key** and **Secret key** showed in the popup
- Fill in the corresponding variables in the `.env` file:
    ```shell
    GW3_ACCESS_KEY=...
    GW3_SECRET_KEY=...
    ```
