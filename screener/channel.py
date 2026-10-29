"""The channel a candidate is talking through (D94): text, a page with a button to choose a time, or voice. A channel is a small
settings value, so the code asks it what to do instead of passing flags down. The candidate's usual channel (text or button) is
saved with them; voice is chosen per message, so the same person can write the next one."""
from dataclasses import dataclass, replace

from screener.client import Client
from screener.phrasing import slot_label, spoken_label


@dataclass(frozen=True)
class Channel:
    name: str
    offer: str  # how a free time is offered: "list" (numbered), "button" (a button opens the times) or "spoken" (day, then time)
    model_words: bool  # the model words the replies; False: the fixed texts only (speech has no time for a second model call)
    accepts_cv: bool  # a file can be sent
    spoken_labels: bool  # a time is said with full words ("el jueves 29 de octubre a las 9:15") instead of "jue 29 oct, 09:15"

    def label(self, starts_at, language) -> str:
        return (spoken_label if self.spoken_labels else slot_label)(starts_at, language)


TEXT = Channel("text", "list", True, True, False)
BUTTON = Channel("button", "button", True, True, False)
VOICE = Channel("voice", "spoken", False, False, True)


def can_speak(client: Client) -> bool:
    """A client that books calls and has the spoken texts."""
    slots = client.spec.pack.slots
    return bool(client.calendar and slots and slots.voice)


def has_button_texts(client: Client) -> bool:
    slots = client.spec.pack.slots
    return bool(client.calendar and slots and slots.offer_button)


def effective(channel: Channel, client: Client) -> Channel:
    """What the channel can do for this client: when the client lacks the texts it needs, times are offered as the numbered list
    and named as in writing. Voice still has no model wording and no file."""
    if channel.offer == "spoken" and not can_speak(client):
        return replace(channel, offer="list", spoken_labels=False)
    if channel.offer == "button" and not has_button_texts(client):
        return replace(channel, offer="list")
    return channel
