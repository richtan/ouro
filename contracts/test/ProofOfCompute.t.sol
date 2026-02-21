// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/ProofOfCompute.sol";

contract ProofOfComputeTest is Test {
    ProofOfCompute public poc;

    function setUp() public {
        poc = new ProofOfCompute();
    }

    function testSubmitProof() public {
        string memory jobId = "test-job-001";
        bytes32 outputHash = keccak256("hello world output");

        poc.submitProof(jobId, outputHash);

        assertEq(poc.proofCount(), 1);

        (bytes32 hash, uint256 ts, address submitter) = poc.verifyProof(jobId);
        assertEq(hash, outputHash);
        assertGt(ts, 0);
        assertEq(submitter, address(this));
    }

    function testCannotSubmitDuplicate() public {
        string memory jobId = "test-job-002";
        bytes32 outputHash = keccak256("output data");

        poc.submitProof(jobId, outputHash);

        vm.expectRevert("Proof already exists");
        poc.submitProof(jobId, outputHash);
    }

    function testVerifyNonexistent() public {
        vm.expectRevert("No proof found");
        poc.verifyProof("nonexistent-job");
    }

    function testMultipleProofs() public {
        for (uint256 i = 0; i < 5; i++) {
            string memory jobId = string(abi.encodePacked("job-", vm.toString(i)));
            bytes32 outputHash = keccak256(abi.encodePacked("output-", vm.toString(i)));
            poc.submitProof(jobId, outputHash);
        }
        assertEq(poc.proofCount(), 5);
    }

    function testReputation() public {
        (uint256 count, uint256 firstTs) = poc.getReputation(address(this));
        assertEq(count, 0);
        assertEq(firstTs, 0);

        poc.submitProof("rep-job-1", keccak256("out1"));
        (count, firstTs) = poc.getReputation(address(this));
        assertEq(count, 1);
        assertGt(firstTs, 0);

        uint256 savedTs = firstTs;

        vm.warp(block.timestamp + 100);
        poc.submitProof("rep-job-2", keccak256("out2"));
        (count, firstTs) = poc.getReputation(address(this));
        assertEq(count, 2);
        assertEq(firstTs, savedTs);
    }

    function testReputationPerSubmitter() public {
        poc.submitProof("s1-job", keccak256("out1"));

        address other = address(0xBEEF);
        vm.prank(other);
        poc.submitProof("s2-job", keccak256("out2"));

        (uint256 myCount,) = poc.getReputation(address(this));
        (uint256 otherCount,) = poc.getReputation(other);
        assertEq(myCount, 1);
        assertEq(otherCount, 1);
        assertEq(poc.proofCount(), 2);
    }
}
