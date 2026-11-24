"""Catálogo de referencias. Los campos ausentes requieren captura local."""

import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def catalog():
    resource = files("hcnet").joinpath("resources", "transit_catalog.json")
    return tuple(json.loads(resource.read_text(encoding="utf-8"))["systems"])


def system_for(identifier):
    return next(system for system in catalog() if system["id"] == identifier)


def vehicle_for(system, identifier):
    return next(
        (vehicle for vehicle in system_for(system)["vehicles"] if vehicle["id"] == identifier), None
    )
