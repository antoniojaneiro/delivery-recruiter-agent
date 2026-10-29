"""D88: what Grupo Sazón says about itself is written once: the service areas with their country, and the two-language
helper both text packs use. A new city is added in one place and cannot be left without a country."""
from sazon.areas import AREAS, AREAS_BY_COUNTRY, COUNTRY_OF
from sazon import pack, ui_pack
from sazon.client import SAZON_CALENDAR


def test_every_service_area_is_listed_once_under_its_country_and_the_calendar_reads_the_same_list():
    listed = [city for cities in AREAS_BY_COUNTRY.values() for city in cities]
    assert sorted(listed) == sorted(set(listed)) and set(listed) == set(AREAS)  # once each, none missing
    assert SAZON_CALENDAR.country_of == COUNTRY_OF == {
        city: country for country, cities in AREAS_BY_COUNTRY.items() for city in cities}
    assert set(AREAS_BY_COUNTRY) <= set(SAZON_CALENDAR.timezones)


def test_both_text_packs_use_the_same_two_language_helper():
    assert pack.bi is ui_pack.bi
