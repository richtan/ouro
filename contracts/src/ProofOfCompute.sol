// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract ProofOfCompute {
    struct Proof {
        bytes32 outputHash;
        uint256 timestamp;
        address submitter;
    }

    mapping(bytes32 => Proof) public proofs;
    uint256 public proofCount;

    mapping(address => uint256) public submitterProofCount;
    mapping(address => uint256) public submitterFirstProof;

    event ProofSubmitted(bytes32 indexed jobHash, bytes32 outputHash, address submitter);

    function submitProof(string calldata jobId, bytes32 outputHash) external {
        bytes32 jobHash = keccak256(abi.encodePacked(jobId));
        require(proofs[jobHash].timestamp == 0, "Proof already exists");
        proofs[jobHash] = Proof(outputHash, block.timestamp, msg.sender);
        proofCount++;

        if (submitterFirstProof[msg.sender] == 0) {
            submitterFirstProof[msg.sender] = block.timestamp;
        }
        submitterProofCount[msg.sender]++;

        emit ProofSubmitted(jobHash, outputHash, msg.sender);
    }

    function verifyProof(string calldata jobId)
        external
        view
        returns (bytes32 outputHash, uint256 timestamp, address submitter)
    {
        bytes32 jobHash = keccak256(abi.encodePacked(jobId));
        Proof memory p = proofs[jobHash];
        require(p.timestamp != 0, "No proof found");
        return (p.outputHash, p.timestamp, p.submitter);
    }

    function getReputation(address submitter)
        external
        view
        returns (uint256 totalProofs, uint256 firstProofTimestamp)
    {
        return (submitterProofCount[submitter], submitterFirstProof[submitter]);
    }
}
