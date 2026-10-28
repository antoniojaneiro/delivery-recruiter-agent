"""Golden snapshot of everything the reuse refactor (D63) must not change for Sazón: fixed texts in both languages,
the model prompt and schema, the consent hash, the recruiter card, the funnel labels and the saved-state format.
Regenerate on purpose with `SAZON_UPDATE_GOLDEN=1 python -m pytest tests/test_characterization.py`."""
import json
import os
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from screener import extraction, funnel, phrasing, summary
from sazon.spec import SAZON, SYSTEM, Extraction
from screener.model import Language, Outcome
from sazon.fields import Field, Reason
from screener.directive import Directive, Kind
from screener.screening import Screening
from screener.store import Store

GOLDEN = Path(__file__).parent / "golden" / "sazon_texts.json"
AREAS = {"Madrid": ["Getafe"], "Guadalajara": ["Zapopan"]}
TODAY = date(2026, 10, 25)
LANGS = (Language.ES, Language.EN)


class NoModel:
    def complete(self, system, user, json_mode=False):
        from screener.llm import LLMError
        raise LLMError("offline")


def _say(directive: Directive, language) -> str:
    return phrasing.phrase(NoModel(), SAZON, directive, language)


def _fixed_texts() -> dict:
    out = {"consent": phrasing.consent_message(SAZON), "closed": phrasing.closed_message(SAZON),
           "consent_hash": phrasing.consent_text_hash(SAZON)}
    fields = [f for f in Field if f != Field.CONSENT]
    for lang in LANGS:
        for field in fields:
            out[f"ask/{field}/{lang}"] = _say(Directive(Kind.ASK, field=field), lang)
            out[f"blocked/{field}/{lang}"] = _say(Directive(Kind.BLOCKED, field=field), lang)
        out[f"confirm_area/{lang}"] = _say(Directive(Kind.CONFIRM_AREA, suggestion="Madrid"), lang)
        for field in (Field.LICENSE, Field.CITY):
            out[f"confirm_rejection/{field}/{lang}"] = _say(
                Directive(Kind.CONFIRM_REJECTION, field=field, suggestion="Leeds"), lang)
        out[f"confirm_change/{lang}"] = _say(Directive(Kind.CONFIRM_CHANGE, options=["a", "b"]), lang)
        for step in ("first", "taken", "unclear", "reminder"):
            out[f"offer/{step}/{lang}"] = _say(Directive(Kind.OFFER_SLOTS, reason=step, options=["x", "y"]), lang)
        out[f"booked/{lang}"] = _say(Directive(Kind.SLOT_BOOKED, label="mar 3 nov, 10:00"), lang)
        out[f"already_booked/{lang}"] = _say(Directive(Kind.ALREADY_BOOKED, label="mar 3 nov, 10:00"), lang)
        out[f"reminder/{lang}"] = _say(Directive(Kind.REMINDER), lang)
        out[f"error/{lang}"] = _say(Directive(Kind.TECHNICAL_ERROR), lang)
        out[f"follow_up/{lang}"] = _say(Directive(Kind.FOLLOW_UP, field=Field.NAME, reason="need last name"), lang)
        out[f"slot_cancelled/{lang}"] = phrasing.slot_cancelled_message(SAZON, lang)
        out[f"tech/{lang}"] = phrasing.technical_error_message(SAZON, lang)
        for notice in ("human", "pay", "human+pay", "changed", "kept", "offtopic"):
            out[f"notice/{notice}/{lang}"] = _say(Directive(Kind.ASK, field=Field.NAME, notices=tuple(notice.split("+"))), lang)
        for outcome in Outcome:
            for repeat in (False, True):
                out[f"close/{outcome}/{repeat}/{lang}"] = _say(
                    Directive(Kind.CLOSE, outcome=outcome, repeat=repeat), lang)
        for reason in Reason:
            for repeat in (False, True):
                out[f"close/DISQ/{reason}/{repeat}/{lang}"] = _say(
                    Directive(Kind.CLOSE, outcome=Outcome.DISQUALIFIED, reasons=[reason], repeat=repeat), lang)
        values = {Field.LICENSE: [True, False], Field.AVAILABILITY: [["full_time", "weekends"]],
                  Field.SCHEDULE: ["evening"], Field.EXPERIENCE: [(0, []), (1, ["glovo"]), (2.5, [])],
                  Field.START_DATE: [date(2026, 11, 1)], Field.NAME: ["Ana Ruiz"], Field.CITY: ["Madrid"]}
        for field, items in values.items():
            for i, value in enumerate(items):
                out[f"describe/{field}/{i}/{lang}"] = phrasing.describe_value(SAZON, field, value, lang)
        out[f"slot_label/{lang}"] = phrasing.slot_label(datetime(2026, 11, 3, 10, 0), lang)
        out[f"cv/offer/{lang}"] = _say(Directive(Kind.CV_OFFER), lang)
        out[f"cv/read_back/{lang}"] = _say(Directive(Kind.CV_READ, options=["Ana Ruiz", "Madrid"]), lang)
        for name in ("notice", "unreadable", "invalid", "not_now"):
            out[f"cv/{name}/{lang}"] = getattr(SAZON.pack.cv, name)[lang]
    out["cv/notice_hash"] = phrasing.cv_notice_hash(SAZON)
    return out


def _prompts() -> dict:
    llm = _Recorder()
    extraction.extract(llm, SAZON, "hola", Field.CITY, "Madrid", TODAY, last_question="¿Dónde?", previous_answer="x",
                       awaiting_rejection=Field.LICENSE)
    return {"extraction_system": SYSTEM, "extraction_user": llm.user,
            "extraction_schema": Extraction.model_json_schema(),
            "phrasing_system": phrasing._system_prompt(SAZON), "cv_system": extraction.build_cv_prompt(SAZON)}


class _Recorder:
    def complete(self, system, user, json_mode=False):
        self.user = user
        return "{}"


def _complete_screening() -> Screening:
    s = Screening(AREAS, SAZON)
    s.record_consent(True)
    answers = {"name": "Juan Pérez", "experience": (2, ["glovo", "uber eats"]), "availability": ["full_time"],
               "schedule": "morning", "start_date": date(2027, 3, 1), "city": "Madrid", "license": True}
    for field, value in answers.items():
        s.submit(field, value, TODAY)
    return s


def _cards() -> dict:
    full = _complete_screening()
    partial = Screening(AREAS, SAZON)
    partial.record_consent(True)
    partial.submit("name", "Ana Ruiz", TODAY)
    partial.submit("license", False, TODAY)
    partial.submit("license", False, TODAY)
    declined = Screening(AREAS, SAZON)
    declined.record_consent(False)
    blocked = Screening(AREAS, SAZON)
    blocked.record_consent(True)
    for _ in range(7):
        blocked.submit("name", "x", TODAY)
    return {"full": summary.summarise(full), "partial": summary.summarise(partial),
            "declined": summary.summarise(declined), "blocked": summary.summarise(blocked),
            "outcome_labels": {str(k): v for k, v in SAZON.recruiter[Language.ES].outcome_labels.items()},
            "field_labels": {f.key: f.label[Language.ES] for f in SAZON.fields}}


def _funnel_stages() -> list:
    with TemporaryDirectory() as folder:
        return [name for name, _ in funnel.build_funnel(Store(Path(folder) / "s.db"), SAZON).stages]


def _state() -> dict:
    s = _complete_screening()
    s.submit("name", "Pedro Gómez", TODAY)  # unchanged slots stay as they are
    s._pending_change = (Field.CITY, "Zapopan", "Madrid", "Guadalajara")
    s._slot_offer = [3, 4, 5]
    s.events.append(("off_topic", ""))
    return s.to_state()


def snapshot() -> dict:
    return {"texts": _fixed_texts(), "prompts": _prompts(), "cards": _cards(), "funnel_stages": _funnel_stages(),
            "state": _state()}


def _roundtrip(data):
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def test_sazon_texts_prompts_cards_and_state_are_unchanged():
    current = _roundtrip(snapshot())
    if os.environ.get("SAZON_UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for section in expected:
        assert current[section] == expected[section], section


def test_a_state_saved_by_the_first_release_still_loads():
    saved = json.loads(GOLDEN.read_text(encoding="utf-8"))["state"]
    loaded = Screening.from_state(AREAS, saved, SAZON)
    assert _roundtrip(loaded.to_state()) == saved
    assert loaded.awaiting_change
    assert loaded.values["city"] == "Madrid"
