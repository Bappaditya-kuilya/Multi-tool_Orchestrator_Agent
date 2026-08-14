from __future__ import annotations

import pytest

from conftest import with_guard
from src.tools.mock_calculator import safe_eval


def test_pow_exponent_bounded():
    with pytest.raises(ValueError):
        with_guard(safe_eval, "9**9**9", timeout_s=1)
    with pytest.raises(ValueError):
        with_guard(safe_eval, "2**1000000", timeout_s=1)
