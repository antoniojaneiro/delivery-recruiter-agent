import time

import pytest


@pytest.fixture(autouse=True)
def _stay_under_the_free_tiers_rate_limit():
    """The free tier allows 15 requests a minute: a short pause before each real-model test keeps a run under it."""
    time.sleep(4)
    yield
