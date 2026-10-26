import pytest

from sazon import accounts


@pytest.fixture(autouse=True)
def _fresh_login_throttle():
    accounts.reset_throttle()
