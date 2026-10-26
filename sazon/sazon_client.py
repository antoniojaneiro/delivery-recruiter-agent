"""Grupo Sazón as a client of the engine (D63)."""
from sazon import config
from sazon.client import Client
from sazon.sazon_spec import SAZON

SAZON_CLIENT = Client(spec=SAZON, areas=config.AREAS)
