"""Internal simulator contract; does not install/register a host hook."""

def simulate_stop(gate_call, *, stop_hook_active=False, attempt=0, max_attempts=2):
    if stop_hook_active or attempt >= max_attempts:
        return {"decision": "block", "reason": "Review loop stopped: blocked; manual review required"}
    try:
        result = gate_call()
        if not isinstance(result, dict) or result.get("allow_completion") is not True or result.get("status") != "pass" or not result.get("evidence_refs"):
            return {"decision": "block", "reason": "Completion review incomplete or invalid; keep blocked"}
        return {}
    except Exception:
        return {"decision": "block", "reason": "Completion review unavailable; fail closed"}
