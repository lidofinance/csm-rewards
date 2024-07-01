// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.24;

interface ICSFeeDistributor {
    function treeCid() external view returns (string memory);
    function treeRoot() external view returns (bytes32);
}
