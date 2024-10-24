// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.24;

interface ICSFeeDistributor {
    event DistributionDataUpdated(
        uint256 totalClaimableShares,
        bytes32 treeRoot,
        string treeCid
    );

    function treeCid() external view returns (string memory);
    function treeRoot() external view returns (bytes32);
}
