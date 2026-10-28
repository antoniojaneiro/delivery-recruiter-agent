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
records = ui.candidates()
by_id = {r.candidate_id: r for r in records}
if "cal_week" not in st.session_state:
    st.session_state["cal_week"] = week_start(date.today())
start = st.session_state["cal_week"]  # the week and country the grid shows also bound the list below it
shown_country = st.session_state.get("cal_country") or list(calendar.timezones)[0]

grid_box = st.container()
avail_box = st.container()
schedule_box = st.container()
manage_box = st.container()

with manage_box:
    with st.expander(t("slots.add_title")):
        team = {r.email: r for r in store.recruiters()}
        owners = list(team) if ui.is_manager() else [e for e in team if e == recruiter]  # a recruiter adds for themselves only
        with st.form("slot_form"):
            caller = st.selectbox(t("slots.caller"), owners, key="slot_recruiter",
                                  format_func=lambda e: f"{team[e].name} ({view.country_label(team[e].country)})")
            day = st.date_input(t("slots.day"), key="slot_date")
            hour = st.time_input(t("slots.hour"), value=time(10, 0), step=900, key="slot_time")
            save = st.form_submit_button(t("slots.add"), key="save_slot", disabled=not owners)

        if save:
            try:
                if not recruiter:
                    raise ValueError(t("common.need_name"))
                store.add_slot(team[caller].country, datetime.combine(day, hour), caller, recruiter, datetime.now().astimezone())
            except (ValueError, LookupError) as error:
                st.error(view.explain_error(error))
            else:
                st.success(t("slots.added"))

    now = datetime.now().astimezone()
    slots = store.listed_slots(now, shown_country, start, start + timedelta(days=7))

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
                slots = store.listed_slots(now, shown_country, start, start + timedelta(days=7))

        if not slots:
            st.info(t("slots.none"))
        else:
            def state(slot) -> str:
                booked = by_id.get(slot.candidate_id)
                return view.slot_state(slot, view.name_of(booked) if booked else None, now)

            st.dataframe(
                [{t("col.id"): s.id, t("slots.country"): view.country_label(s.country),
                  t("slots.col_when"): slot_label(s.starts_at, language), t("slots.col_caller"): s.recruiter or "",
                  t("slots.col_state"): state(s)} for s in slots],
                hide_index=True, width="stretch")

# --- organising a call for a candidate ----------------------------------------------------------------------------------
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
            free = store.free_slots(where, now, FREE_TIMES_SHOWN, as_recruiter=True) if where else []
            if record.booking:  # the time they already have is not an option to move to
                free = [s for s in free if s.id != record.booking.slot_id]
            if not free:
                st.caption(t("sched.no_free"))
            slot_id = st.selectbox(t("sched.slot"), [s.id for s in free], index=None, key="sched_slot",
                                   placeholder=t("sched.candidate_placeholder"),
                                   format_func=lambda sid: slot_label(next(s.starts_at for s in free if s.id == sid), language))
            moving = record.booking is not None

            def organise(book) -> None:
                """Books or moves the call and says what happened; a refused booking says why."""
                try:
                    done = book()
                except (InputError, LookupError, ValueError) as error:
                    st.error(view.explain_error(error))
                    return
                st.success(t("sched.moved" if done.before else "sched.done", name=escape_markdown(view.name_of(record)),
                             label=slot_label(done.booking.starts_at, language)))
                if not done.told:  # the booking stands; only the notice in their chat could not be saved
                    st.warning(t("slots.notice_failed"))

            if st.button(t("sched.submit_move") if moving else t("sched.submit"), key="sched_submit",
                         disabled=slot_id is None, icon=":material/event_available:"):
                organise(lambda: slot_flow.schedule_by_recruiter(store, SAZON_CLIENT, chosen, slot_id, recruiter, datetime.now()))

            st.markdown(f"**{t('sched.new_title')}**")
            in_country = [r.email for r in store.recruiters() if r.country == where]  # only a recruiter of that country takes it
            owner = (st.selectbox(t("sched.new_owner"), in_country, key="sched_new_owner", index=0 if in_country else None)
                     if ui.is_manager() else (recruiter if recruiter in in_country else None))
            if owner is None:
                st.caption(t("sched.new_owner_none"))
            with st.container(horizontal=True, vertical_alignment="bottom"):
                new_day = st.date_input(t("sched.new_day"), key="sched_new_day")
                new_hour = st.time_input(t("sched.new_hour"), value=time(10, 0), step=900, key="sched_new_hour")
                create = st.button(t("sched.submit_new"), key="sched_submit_new", disabled=owner is None,
                                   icon=":material/add_circle:")
            if create:  # the time is the owner's, in the candidate's own country, then booked like any other
                organise(lambda: slot_flow.schedule_new_time(store, SAZON_CLIENT, chosen, where, datetime.combine(new_day, new_hour),
                                                             owner, recruiter, datetime.now()))

# --- a recruiter's own week and days off ---------------------------------------------------------------------------------
with avail_box:
    st.subheader(t("avail.title"))
    st.caption(t("avail.caption"))
    people = store.recruiters()
    if ui.is_manager():  # the hiring manager may edit anyone's week
        who = st.selectbox(t("avail.who"), [p.email for p in people], key="avail_who", index=0 if people else None,
                           format_func=lambda e: next(f"{p.name} ({p.email})" for p in people if p.email == e)) if people else None
    else:
        who = recruiter if store.get_recruiter(recruiter) else None
    if who is None:
        st.caption(t("avail.none_who"))
    else:
        if st.session_state.get("_avail_for") != who:  # another person's week: start the boxes from theirs
            for key in [k for k in st.session_state if k.startswith(("avail_on_", "avail_start_", "avail_end_"))]:
                del st.session_state[key]
            st.session_state["_avail_for"] = who
        if flash := st.session_state.pop("_avail_flash", None):
            st.success(flash)
        week_now = {w: (s, e) for w, s, e in store.weekly(who)}
        picks = []
        for weekday in range(7):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                on = st.checkbox(t(f"cal.day.{weekday}"), value=weekday in week_now, key=f"avail_on_{weekday}")
                first, last = week_now.get(weekday, (calendar.default_start, calendar.default_end))
                start_at = st.time_input(t("avail.start"), value=time(first // 60, first % 60), step=900,
                                         key=f"avail_start_{weekday}", disabled=not on, width=140)
                end_at = st.time_input(t("avail.end"), value=time(last // 60, last % 60), step=900,
                                       key=f"avail_end_{weekday}", disabled=not on, width=140)
            if on:
                picks.append((weekday, start_at.hour * 60 + start_at.minute, end_at.hour * 60 + end_at.minute))

        def changed(change) -> None:
            done = change()
            text = t("avail.saved")
            if done.moved or done.released:
                text += " " + t("avail.effect", moved=done.moved, released=done.released)
            st.session_state["_avail_flash"] = text
            for key in [k for k in st.session_state if k.startswith(("avail_on_", "avail_start_", "avail_end_"))]:
                del st.session_state[key]
            st.rerun()

        with st.container(horizontal=True):
            if st.button(t("avail.save"), key="avail_save", icon=":material/save:", type="primary"):
                try:
                    changed(lambda: slot_flow.save_week(store, SAZON_CLIENT, who, picks, recruiter, datetime.now()))
                except InputError as error:
                    st.error(view.explain_error(error))
            if st.button(t("avail.reset"), key="avail_reset"):
                changed(lambda: slot_flow.reset_week(store, SAZON_CLIENT, who, recruiter, datetime.now()))
        with st.container(horizontal=True, vertical_alignment="bottom"):
            off_day = st.date_input(t("avail.off_day"), key="off_day")
            if st.button(t("avail.off_add"), key="off_add"):
                changed(lambda: slot_flow.set_day_off(store, SAZON_CLIENT, who, off_day, True, recruiter, datetime.now()))
        for day_off in store.days_off(who):
            if day_off >= date.today() and st.button(t("avail.off_remove", day=f"{day_off:%d/%m/%Y}"),
                                                     key=f"off_remove_{day_off.isoformat()}", icon=":material/close:"):
                changed(lambda day_off=day_off: slot_flow.set_day_off(store, SAZON_CLIENT, who, day_off, False, recruiter, datetime.now()))

# --- the week grid (drawn above, filled last so it shows everything just changed) ---------------------------------------
def shift_week(days: int | None) -> None:
    st.session_state["cal_week"] = week_start(date.today()) if days is None else st.session_state["cal_week"] + timedelta(days=days)


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
    st.segmented_control(t("cal.scope"), ["mine", "all"], default="all" if ui.is_manager() else "mine", key="cal_scope",
                         format_func=lambda value: t(f"cal.scope_{value}"), label_visibility="collapsed")
    everyone = (st.session_state.get("cal_scope") or "all") == "all"
    zone = calendar.zone(shown_country)
    local_now = datetime.now(zone).replace(tzinfo=None)  # the country's own clock: a time is past by that clock
    names = {r.email: r.name for r in store.recruiters()}
    week = week_slots(store.booked_slots(shown_country, start, start + timedelta(days=7)), start, shown_country)
    columns = st.columns(7)
    for column, (day, found) in zip(columns, week.items()):
        with column:
            st.markdown(f"**{t(f'cal.day.{day.weekday()}')} {day.day}**" + (" ·" if day == date.today() else ""))
            for item in (i for i in found if everyone or i.recruiter == recruiter):
                booked = by_id.get(item.candidate_id)
                who = f" · {names.get(item.recruiter, item.recruiter or '')}" if everyone else ""
                label = f"{item.starts_at:%H:%M} · {escape_markdown(view.name_of(booked)) if booked else '?'}{who}"
                st.markdown(f":gray-badge[{label}]" if item.starts_at < local_now else f":blue-badge[{label}]")
            free_count = len(store.free_slots_on(shown_country, day, now, as_recruiter=True)) if day >= date.today() else 0
            if free_count:
                st.caption(t("cal.free", n=free_count))
    st.caption(t("cal.legend"))
