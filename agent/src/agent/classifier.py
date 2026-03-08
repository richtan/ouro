"""Classify job failures as platform_error or user_error.

Classification is based on Slurm state (which users cannot forge from inside
Docker containers with --network none, --cap-drop ALL) rather than exit codes.
"""

from __future__ import annotations


def classify_failure(
    failure_stage: int | None,
    reason: str,
    exit_code: int | None = None,
    slurm_state: str | None = None,
) -> str:
    """Return 'platform_error' or 'user_error' based on failure context.

    Stage 1: validation / capacity
    Stage 2: Slurm submission
    Stage 3: Slurm execution / polling
    """
    # Stage 1: validation errors are user errors, capacity failures are platform errors
    if failure_stage == 1:
        reason_lower = (reason or "").lower()
        if "capacity" in reason_lower or "no node" in reason_lower or "scaling" in reason_lower:
            return "platform_error"
        return "user_error"

    # Stage 2: Slurm submission failures are infrastructure errors
    if failure_stage == 2:
        return "platform_error"

    # Stage 3: classify by Slurm state
    if failure_stage == 3 and slurm_state:
        upper = slurm_state.upper()
        # States users cannot trigger from inside Docker
        if upper in ("CANCELLED", "NODE_FAIL"):
            return "platform_error"
        # User code ran and failed or timed out
        if upper in ("FAILED", "TIMEOUT"):
            return "user_error"
        # Stuck PENDING = no suitable node
        if upper == "PENDING":
            return "platform_error"

    # Poll timeout, asyncio.TimeoutError, unhandled exceptions → platform error
    reason_lower = (reason or "").lower()
    if "timeout" in reason_lower and "polling" in reason_lower:
        return "platform_error"

    # Default: benefit of the doubt
    return "platform_error"
