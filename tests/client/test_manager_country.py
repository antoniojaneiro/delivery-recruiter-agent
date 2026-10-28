"""D89: the country whose calls the hiring manager takes comes from .env (HIRING_MANAGER_COUNTRY), Spain when it is not set
or is not one of the client's countries."""
from sazon import config
from tests.support.tables import table


@table("value,expected", [(None, "ES"), ("", "ES"), ("MX", "MX"), (" mx ", "MX"), ("es", "ES"), ("FR", "ES"), ("Mexico", "ES")])
def test_the_managers_country_is_read_from_the_environment_with_spain_as_the_default(value, expected):
    import os
    old = os.environ.pop("HIRING_MANAGER_COUNTRY", None)
    try:
        if value is not None:
            os.environ["HIRING_MANAGER_COUNTRY"] = value
        assert config.manager_country() == expected
    finally:
        os.environ.pop("HIRING_MANAGER_COUNTRY", None)
        if old is not None:
            os.environ["HIRING_MANAGER_COUNTRY"] = old
