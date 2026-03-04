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
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ERC-8004 Reputation Registry — on-chain feedback for agents
ERC8004_REPUTATION_ABI = [
    {
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "score", "type": "uint8"},
            {"name": "weight", "type": "uint256"},
            {"name": "serviceType", "type": "string"},
            {"name": "comment", "type": "string"},
            {"name": "endpoint", "type": "string"},
            {"name": "extra", "type": "string"},
            {"name": "ref", "type": "bytes32"},
        ],
        "name": "giveFeedback",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "filters", "type": "string[]"},
            {"name": "serviceType", "type": "string"},
            {"name": "endpoint", "type": "string"},
        ],
        "name": "getSummary",
        "outputs": [
            {"name": "totalScore", "type": "uint256"},
            {"name": "count", "type": "uint256"},
            {"name": "weightedSum", "type": "uint256"},
            {"name": "totalWeight", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "reviewer", "type": "address"},
            {"name": "serviceType", "type": "string"},
            {"name": "endpoint", "type": "string"},
        ],
        "name": "readFeedback",
        "outputs": [
            {"name": "score", "type": "uint8"},
            {"name": "weight", "type": "uint256"},
            {"name": "comment", "type": "string"},
            {"name": "timestamp", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

MULTICALL3_ABI = [
    {
        "inputs": [
            {"name": "requireSuccess", "type": "bool"},
            {
                "components": [
                    {"name": "target", "type": "address"},
                    {"name": "callData", "type": "bytes"},
                ],
                "name": "calls",
                "type": "tuple[]",
            },
        ],
        "name": "tryAggregate",
        "outputs": [
            {
                "components": [
                    {"name": "success", "type": "bool"},
                    {"name": "returnData", "type": "bytes"},
                ],
                "name": "returnData",
                "type": "tuple[]",
            },
        ],
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
