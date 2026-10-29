"""D94: where a voice call stands is one pure answer, so the chat page only draws it. A call is not set up here, ready to start,
running, or done (after a call, or by text alone); a running call wins until the page closes it, and a finished call is closed
by the page itself a little after the conversation is over when the call page could not."""
from datetime import datetime, timedelta

from screener.voice_call import DONE_AFTER_CALL, DONE_BY_TEXT, NOT_SET_UP, READY, RUNNING, call_state, should_close
from tests.support.tables import table


@table("set_up,running,over,had_call,state", [
    (False, False, False, False, NOT_SET_UP),
    (True, False, False, False, READY),
    (True, True, False, False, RUNNING),
    (True, True, True, True, RUNNING),          # over, but the call is still drawn until it closes
    (True, False, True, True, DONE_AFTER_CALL),
    (True, False, True, False, DONE_BY_TEXT),
    (False, False, True, True, DONE_AFTER_CALL),  # finished is finished, whether or not voice is set up now
])
def test_where_a_call_stands(set_up, running, over, had_call, state):
    assert call_state(set_up=set_up, running=running, over=over, had_call=had_call) == state


def test_a_finished_call_is_closed_by_the_page_after_a_short_grace():
    started = datetime(2026, 10, 29, 12, 0, 0)
    assert should_close(None, started) is False  # the conversation is not over
    assert should_close(started, started + timedelta(seconds=10)) is False  # the farewell may still be being spoken
    assert should_close(started, started + timedelta(seconds=31)) is True
    assert should_close(started, started + timedelta(seconds=31), grace_seconds=60) is False
