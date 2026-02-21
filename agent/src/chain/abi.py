"""Minimal ABI definitions for on-chain interactions."""

ERC20_BALANCE_OF_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

PROOF_OF_COMPUTE_ABI = [
    {
        "inputs": [
            {"name": "jobId", "type": "string"},
            {"name": "outputHash", "type": "bytes32"},
        ],
        "name": "submitProof",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "jobId", "type": "string"}],
        "name": "verifyProof",
        "outputs": [
            {"name": "outputHash", "type": "bytes32"},
            {"name": "timestamp", "type": "uint256"},
            {"name": "submitter", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "proofCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "jobHash", "type": "bytes32"},
            {"indexed": False, "name": "outputHash", "type": "bytes32"},
            {"indexed": False, "name": "submitter", "type": "address"},
        ],
        "name": "ProofSubmitted",
        "type": "event",
    },
]

CODE_REGISTRY_ABI = [
    {
        "inputs": [{"name": "code", "type": "string"}],
        "name": "isRegistered",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "code", "type": "string"}],
        "name": "payoutAddress",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

ERC8004_ABI = [
    {
        "inputs": [{"name": "agentURI", "type": "string"}],
        "name": "register",
        "outputs": [{"name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "agentCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

PROOF_OF_COMPUTE_REPUTATION_ABI = [
    {
        "inputs": [{"name": "submitter", "type": "address"}],
        "name": "getReputation",
        "outputs": [
            {"name": "totalProofs", "type": "uint256"},
            {"name": "firstProofTimestamp", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]
