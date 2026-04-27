// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.24;

// @notice Local stub used to generate Wake pytypes for off-chain checks.
interface IFeeDistributor {
    struct DistributionData {
        uint256 refSlot;
        bytes32 treeRoot;
        string treeCid;
        string logCid;
        uint256 distributed;
        uint256 rebate;
    }

    function treeCid() external view returns (string memory);
    function treeRoot() external view returns (bytes32);

    function distributionDataHistoryCount() external view returns (uint256);
    function getHistoricalDistributionData(
        uint256 index
    ) external view returns (DistributionData memory);
}
