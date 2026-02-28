from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Quote:
    price: str
    breakdown: dict = field(default_factory=dict)
    guaranteed_profitable: bool = False


@dataclass
class JobResult:
    job_id: str
    status: str
    output: str = ""
    error_output: str = ""
    output_hash: str | None = None
    proof_tx_hash: str | None = None
    compute_duration_s: float | None = None
    price_usdc: float | None = None
