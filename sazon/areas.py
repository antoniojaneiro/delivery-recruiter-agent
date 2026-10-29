"""Where Grupo Sazón delivers (D13): the service areas, their nearby towns and each area's country."""

# Sample service areas (D13). Replace with the client's real list before any pilot.
# Nearby towns and districts are samples too: they let "Zapopan" or "Chamberí" count as their service area.
AREAS_BY_COUNTRY = {
    "ES": {
        "Madrid": ["Chamberí", "Getafe", "Alcalá de Henares", "Leganés", "Alcorcón"],
        "Barcelona": ["L'Hospitalet de Llobregat", "Hospitalet", "Badalona"],
        "Valencia": ["Paterna", "Torrent"],
    },
    "MX": {
        "Ciudad de México": ["CDMX", "DF", "Mexico City", "Coyoacán", "Iztapalapa", "Tlalpan"],
        "Guadalajara": ["Zapopan", "Tlaquepaque", "Tonalá"],
        "Monterrey": ["San Pedro Garza García", "San Nicolás de los Garza", "Apodaca"],
    },
}
# The same list the engine and the calendar read: each area with its nearby towns, and each area's country.
AREAS = {area: nearby for areas in AREAS_BY_COUNTRY.values() for area, nearby in areas.items()}
COUNTRY_OF = {area: country for country, areas in AREAS_BY_COUNTRY.items() for area in areas}
