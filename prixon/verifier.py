from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    prediction_error: float
    observations: dict[str, Any]
    reason: str


def compare_expected(
    expected: str,
    observed: dict[str, Any],
    *,
    action: str,
) -> VerificationResult:
    """Machine-first postcondition scoring.

    Exact structured outputs are scored deterministically. Fuzzy natural-language
    expectations never become an authorization signal.
    """
    if not observed:
        return VerificationResult(False, 1.0, {}, "no_observation")

    checks = [item.strip() for item in expected.split(",") if item.strip()]
    if not checks:
        return VerificationResult(True, 0.0, observed, "no_machine_check_declared")

    matched = 0
    for check in checks:
        key = check.casefold()
        if "status_snapshot_returned" in key:
            matched += int(bool(observed.get("cpu_percent") is not None))
        elif "process_list_returned" in key:
            matched += int("processes" in observed)
        elif "application_running_state_returned" in key:
            matched += int("running" in observed)
        elif "memory_snapshot_returned" in key:
            matched += int(
                "total_bytes" in observed and "available_bytes" in observed
                and "percent" in observed
            )
        elif "cpu_snapshot_returned" in key:
            matched += int("cpu_percent" in observed and "logical_cores" in observed)
        elif "wifi_status_returned" in key:
            matched += int("connected" in observed and "adapters" in observed)
        elif "audio_level_returned" in key:
            matched += int(observed.get("volume") is not None)
        elif "battery_snapshot_returned" in key:
            matched += int("battery" in observed)
        elif "network_snapshot_returned" in key:
            matched += int("interfaces" in observed and "bytes_sent" in observed)
        elif "target_process_started" in key:
            matched += int(observed.get("pid") is not None)
        elif "window_is_minimized" in key:
            matched += int(bool(observed.get("iconic")))
        elif "window_is_maximized" in key:
            matched += int(bool(observed.get("zoomed")))
        elif "window_is_restored" in key:
            matched += int(not bool(observed.get("iconic")))
        elif "volume_equals_requested_level" in key:
            matched += int(observed.get("volume") is not None)
        elif "settings_page_opened" in key:
            matched += int(bool(observed.get("opened_setting")))
        elif "clipboard_metadata_returned" in key:
            matched += int(
                "formats" in observed and observed.get("content_read") is False
            )
        elif "clipboard_text_returned_without_persistence" in key:
            matched += int(
                isinstance(observed.get("text"), str)
                and observed.get("content_read_explicitly") is True
            )
        elif "file_in_quarantine" in key:
            matched += int(bool(observed.get("quarantined_path")))
        elif "window_closed_or_close_prompt_shown" in key:
            matched += int(bool(observed.get("close_requested")))
        else:
            # Unknown textual expectations are not treated as successful.
            matched += 0

    score = matched / len(checks)
    return VerificationResult(
        verified=score >= 1.0,
        prediction_error=round(1.0 - score, 4),
        observations=observed,
        reason=f"action={action}; checks={matched}/{len(checks)}",
    )
