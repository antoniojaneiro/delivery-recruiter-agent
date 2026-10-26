import pytest

from screener import accounts


@pytest.fixture(autouse=True)
def _fresh_login_throttle():
    accounts.reset_throttle()
