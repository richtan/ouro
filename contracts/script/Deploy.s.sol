// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/ProofOfCompute.sol";

contract DeployScript is Script {
    function run() external {
        vm.startBroadcast();
        ProofOfCompute poc = new ProofOfCompute();
        console.log("ProofOfCompute deployed at:", address(poc));
        vm.stopBroadcast();
    }
}
