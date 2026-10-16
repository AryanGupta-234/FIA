import pytest

from fia.services.offers import should_emit_price_alert


@pytest.mark.parametrize(
    ("drop_percent", "threshold", "within_cooldown", "expected"),
    [
        (13.3, 2.0, False, True),
        (2.0, 2.0, False, True),
        (1.9, 2.0, False, False),
        (25.0, 5.0, True, False),
        (0.0, 0.0, False, True),
    ],
)
def test_price_alert_policy(drop_percent, threshold, within_cooldown, expected):
    assert should_emit_price_alert(drop_percent, threshold, within_cooldown) is expected
