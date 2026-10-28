from datetime import date, datetime, time, timedelta

import streamlit as st

from screener import slot_flow
from screener.calendar_view import week_slots, week_start

from sazon import ui
from sazon.ui import t
from sazon.client import SAZON_CLIENT
from screener.phrasing import slot_label
from screener.recruiter_rules import can_schedule
from screener.recruiter_view import escape_markdown, filter_records
from screener.store import InputError

PICK_CHOICES = 20  # candidates offered to organise a call for; a search narrows them
FREE_TIMES_SHOWN = 40  # the nearest free times offered for one candidate

store = ui.store()
recruiter = ui.recruiter_name()
language = ui.language()
view = ui.view()
spec = SAZON_CLIENT.spec
calendar = store.calendar

st.title(t("slots.title"))
st.caption(t("slots.caption"))

# The page is drawn top to bottom as: the week grid, organising a call, then adding and cancelling times. They are
# worked out in the opposite order, so the grid always shows what was just added, booked or cancelled.
grid_box = st.container()
schedule_box = st.container()
manage_box = st.container()

with manage_box:
    with st.expander(t("slots.add_title")):
        with st.form("slot_form"):
            countries = list(calendar.timezones)
            country = st.selectbox(t("slots.country"), countries, format_func=lambda code: view.country_label(code),
                                   key="slot_country")
            day = st.date_input(t("slots.day"), key="slot_date")
            hour = st.time_input(t("slots.hour"), value=time(10, 0), step=900, key="slot_time")
            caller = st.text_input(t("slots.caller"), key="slot_recruiter")
            save = st.form_submit_button(t("slots.add"), key="save_slot")

        if save:
            try:
                if not recruiter:
                    raise ValueError(t("common.need_name"))
                store.add_slot(country, datetime.combine(day, hour), caller, recruiter, datetime.now().astimezone())
            except (ValueError, LookupError) as error:
                st.error(view.explain_error(error))
            else:
                st.success(t("slots.added"))

    now = datetime.now().astimezone()
    slots = store.slots(now)

    with st.expander(t("slots.list_title"), expanded=bool(slots)):
        if slots:
            def describe(slot_id: int) -> str:
                slot = next(s for s in slots if s.id == slot_id)
                return f"{view.country_label(slot.country)} · {slot_label(slot.starts_at, language)}"

            with st.container(horizontal=True, vertical_alignment="bottom"):
                to_cancel = st.selectbox(t("slots.cancel_pick"), [s.id for s in slots], format_func=describe,
                                         key="cancel_slot")
                cancel = st.button(t("slots.cancel_button"), key="confirm_cancel")
            if cancel:
                if not recruiter:
                    st.error(t("common.need_name"))
                else:
                    try:
                        booked_by = store.cancel_slot(to_cancel, recruiter, now)
                    except (ValueError, LookupError) as error:
                        st.error(view.explain_error(error))
                        st.stop()
                    if booked_by:
                        booked = store.get(booked_by)
                        who = f"{escape_markdown(view.name_of(booked))} ({booked_by})" if booked else booked_by
                        told = slot_flow.notify_cancelled(store, SAZON_CLIENT, booked_by, now.replace(tzinfo=None))
                        st.warning(t("slots.booked_warning", who=who,
                                     notice=t("slots.notice_left") if told else t("slots.notice_failed")))
                    else:
                        st.success(t("slots.cancelled"))
                slots = store.slots(now)

        if not slots:
            st.info(t("slots.none"))
        else:
            def state(slot) -> str:
                booked = store.get(slot.candidate_id) if slot.candidate_id else None
                return view.slot_state(slot, view.name_of(booked) if booked else None, now)

            st.dataframe(
                [{t("col.id"): s.id, t("slots.country"): view.country_label(s.country),
                  t("slots.col_when"): slot_label(s.starts_at, language), t("slots.col_caller"): s.recruiter or "",
                  t("slots.col_state"): state(s)} for s in slots],
                hide_index=True, width="stretch")

# --- organising a call for a candidate ----------------------------------------------------------------------------------
records = ui.candidates()
by_id = {r.candidate_id: r for r in records}
eligible = [r for r in records if can_schedule(r)]


def candidate_label(candidate_id: str) -> str:
    record = by_id[candidate_id]
    text = f"{view.name_of(record)} · {record.extracted.get(spec.area_field, '')} ({candidate_id})"
    if record.booking:
        text += " · " + t("sched.call_now", label=slot_label(record.booking.starts_at, language))
    return text


with schedule_box:
    st.subheader(t("sched.title"))
    st.caption(t("sched.hint"))
    if not eligible:
        st.caption(t("sched.none"))
    else:
        eligible_ids = {r.candidate_id for r in eligible}
        with st.container(horizontal=True, vertical_alignment="bottom"):
            search = st.text_input(t("sched.search"), key="sched_search")
            choices = [r.candidate_id for r in filter_records(eligible, [], [], search, spec, False)[:PICK_CHOICES]]
            kept = st.session_state.get("sched_candidate")
            if kept in eligible_ids and kept not in choices:
                choices.append(kept)  # a chosen candidate stays chosen while the search changes
            if kept not in eligible_ids:
                st.session_state["sched_candidate"] = None  # no longer one a call can be organised for
            chosen = st.selectbox(t("sched.candidate"), choices, index=None, key="sched_candidate",
                                  placeholder=t("sched.candidate_placeholder"), format_func=candidate_label)
        if chosen is not None:
            record = by_id[chosen]
            where = calendar.country_of.get(record.extracted.get(spec.area_field))
            free = store.free_slots(where, now, FREE_TIMES_SHOWN) if where else []
            if record.booking:  # the time they already have is not an option to move to
                free = [s for s in free if s.id != record.booking.slot_id]
            if not free:
                st.caption(t("sched.no_free"))
            slot_id = st.selectbox(t("sched.slot"), [s.id for s in free], index=None, key="sched_slot",
                                   placeholder=t("sched.candidate_placeholder"),
                                   format_func=lambda sid: slot_label(next(s.starts_at for s in free if s.id == sid), language))
            moving = record.booking is not None

            def organise(wanted_slot: int) -> None:
                """Books or moves the call and says what happened; a refused booking says why."""
                try:
                    done = slot_flow.schedule_by_recruiter(store, SAZON_CLIENT, chosen, wanted_slot, recruiter,
                                                           datetime.now())
                except (InputError, LookupError) as error:
                    st.error(view.explain_error(error))
                    return
                st.success(t("sched.moved" if done.before else "sched.done", name=escape_markdown(view.name_of(record)),
                             label=slot_label(done.booking.starts_at, language)))
                if not done.told:  # the booking stands; only the notice in their chat could not be saved
                    st.warning(t("slots.notice_failed"))

            if st.button(t("sched.submit_move") if moving else t("sched.submit"), key="sched_submit",
                         disabled=slot_id is None, icon=":material/event_available:"):
                organise(slot_id)

            st.markdown(f"**{t('sched.new_title')}**")
            with st.container(horizontal=True, vertical_alignment="bottom"):
                new_day = st.date_input(t("sched.new_day"), key="sched_new_day")
                new_hour = st.time_input(t("sched.new_hour"), value=time(10, 0), step=900, key="sched_new_hour")
                create = st.button(t("sched.submit_new"), key="sched_submit_new", disabled=where is None,
                                   icon=":material/add_circle:")
            if create:
                try:  # the time is made in the candidate's own country, then booked like any other
                    new_slot = store.add_slot(where, datetime.combine(new_day, new_hour), recruiter, recruiter, now)
                except (InputError, ValueError) as error:
                    st.error(view.explain_error(error))
                else:
                    organise(new_slot)
                    if store.booking_of(chosen) is None or store.booking_of(chosen).slot_id != new_slot:
                        store.cancel_slot(new_slot, recruiter, now)  # not booked after all: do not leave the time behind

# --- the week grid (drawn above, filled last so it shows everything just changed) ---------------------------------------
if "cal_week" not in st.session_state:
    st.session_state["cal_week"] = week_start(date.today())


def shift_week(days: int | None) -> None:
    st.session_state["cal_week"] = week_start(date.today()) if days is None else st.session_state["cal_week"] + timedelta(days=days)


start = st.session_state["cal_week"]
with grid_box:
    countries = list(calendar.timezones)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.segmented_control(t("slots.country"), countries, default=countries[0], key="cal_country",
                             format_func=lambda code: view.country_label(code), label_visibility="collapsed")
        st.button(t("cal.prev"), key="week_prev", on_click=shift_week, args=(-7,), icon=":material/chevron_left:")
        st.button(t("cal.today"), key="week_today", on_click=shift_week, args=(None,))
        st.button(t("cal.next"), key="week_next", on_click=shift_week, args=(7,), icon=":material/chevron_right:")
        end = start + timedelta(days=6)
        st.markdown(f"**{t('cal.week', first=f'{start:%d/%m}', last=f'{end:%d/%m/%Y}')}**")
    shown_country = st.session_state.get("cal_country") or countries[0]
    zone = calendar.zone(shown_country)
    local_now = datetime.now(zone).replace(tzinfo=None)  # the country's own clock: a time is past by that clock
    week = week_slots(store.slots(now, include_past=True), start, shown_country)
    columns = st.columns(7)
    for column, (day, found) in zip(columns, week.items()):
        with column:
            st.markdown(f"**{t(f'cal.day.{day.weekday()}')} {day.day}**" + (" ·" if day == date.today() else ""))
            for item in found:
                clock = f"{item.starts_at:%H:%M}"
                booked = by_id.get(item.candidate_id) if item.candidate_id else None
                name = f" · {escape_markdown(view.name_of(booked))}" if booked else (" · ?" if item.candidate_id else "")
                if item.starts_at < local_now:
                    st.markdown(f":gray-badge[{clock}{name}]")
                elif item.candidate_id:
                    st.markdown(f":blue-badge[{clock}{name}]")
                else:
                    st.markdown(f":green-badge[{clock}]")
    if not any(week.values()):
        st.caption(t("cal.empty_week"))
    st.caption(t("cal.legend"))
