"""When the dashboard reloads itself. It never interrupts a recruiter who has a candidate open (a half-written note must
survive): then it only offers the update."""
import pytest

from screener.recruiter_view import refresh_action


@pytest.mark.parametrize("seen,current,open_,expected", [
    (5, 5, False, "none"),
    (5, 5, True, "none"),
    (5, 6, False, "reload"),
    (5, 6, True, "offer"),
    (None, 6, False, "none"),  # the page has not loaded a list yet: nothing to compare
    (5, 4, False, "reload"),  # a counter that went backwards (a replaced database) still means "different"
])
def test_the_dashboard_reloads_when_nothing_is_open_and_only_offers_otherwise(seen, current, open_, expected):
    assert refresh_action(seen, current, open_) == expected
