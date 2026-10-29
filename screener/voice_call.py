"""Where a live voice call stands (D93, D94), as one answer a page can draw: not set up here, ready to start, running, or done
(after a call, or because the conversation ended in writing). Pure, so every page that offers a call says the same."""
NOT_SET_UP, READY, RUNNING, DONE_AFTER_CALL, DONE_BY_TEXT = "not_set_up", "ready", "running", "done_after_call", "done_by_text"


def call_state(*, set_up: bool, running: bool, over: bool, had_call: bool) -> str:
    """`running`: the page is drawing a call. `over`: nothing more is left to say. `had_call`: they spoke with the agent."""
    if running:
        return RUNNING  # until the page closes it, even when the conversation is over
    if over:
        return DONE_AFTER_CALL if had_call else DONE_BY_TEXT
    return READY if set_up else NOT_SET_UP


def should_close(over_since, now, grace_seconds: int = 30) -> bool:
    """The page closes a call itself when the conversation has been over for a little while (the farewell is spoken and the call
    has ended), in case the call page could not close it."""
    return over_since is not None and (now - over_since).total_seconds() > grace_seconds
