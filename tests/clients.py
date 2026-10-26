from screener.client import Client
from sazon.client import SAZON_CALENDAR
from sazon.spec import SAZON


def client_for(areas) -> Client:
    """Sazón's screening over the given service areas."""
    return Client(spec=SAZON, areas=areas, calendar=SAZON_CALENDAR)
