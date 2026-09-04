"""The trace and delta pages for the other metrics, to review before they
join the rotation as pools."""
from pages.pool import CO2, IAQ, PM25, TEMP, DeltaPage, TracePage


def candidate_pages(tz, **geometry):
    return [
        TracePage("co2-trace", CO2, tz=tz, **geometry),
        DeltaPage("co2-delta", CO2, tz=tz, **geometry),
        TracePage("comfort-trace", TEMP, tz=tz, **geometry),
        DeltaPage("comfort-delta", TEMP, tz=tz, **geometry),
        TracePage("dust-trace", PM25, tz=tz, **geometry),
        DeltaPage("dust-delta", PM25, tz=tz, **geometry),
        TracePage("air-trace", IAQ, tz=tz, **geometry),
        DeltaPage("air-delta", IAQ, tz=tz, **geometry),
    ]
