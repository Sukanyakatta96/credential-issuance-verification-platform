COMPLETION_STATUSES = ("enrolled", "in_progress", "completed", "failed", "withdrawn")
TERMINAL_STATUSES = ("completed", "failed", "withdrawn")


def derive_completion_state(*, pass_mark: int, max_attempts: int, progress_pct: int,
                            attempt_scores: list[float], withdrawn: bool = False) -> dict:
    attempts_used = len(attempt_scores)
    final_score = max(attempt_scores) if attempt_scores else None
    first_pass_index = next((i for i, s in enumerate(attempt_scores) if s >= pass_mark), None)
    if first_pass_index is not None:
        status = "completed"
    elif withdrawn:
        status = "withdrawn"
    elif attempts_used >= max_attempts:
        status = "failed"
    elif progress_pct > 0 or attempts_used > 0:
        status = "in_progress"
    else:
        status = "enrolled"
    return {
        "status": status,
        "attempts_used": attempts_used,
        "final_score": final_score,
        "first_pass_index": first_pass_index,
    }
