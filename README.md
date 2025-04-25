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
