"""Casos sintéticos reproducibles, cargados mediante una acción explícita."""

from dataclasses import asdict

from hcnet.domain.transit_catalog import vehicle_for
from hcnet.domain.transit_engineering import Door

DEMONSTRATIONS = (
    "RTP · Autobús convencional",
    "Metrobús · Corredor confinado",
    "Metro · Ferrocarril pesado",
    "Cablebús · Cabinas continuas",
    "Combi · Servicio de baja demanda",
    "Selección preliminar de tecnología",
    "Calibración de congestión BPR",
)


def _line(system, model, length, speed, headway, nominal, demand, cars, door_count):
    doors = [asdict(Door(car=min(cars, i * cars // door_count + 1))) for i in range(door_count)]
    reference = vehicle_for(system, model)
    return {
        "system": system,
        "selection": model,
        "reference": reference,
        "vehicle": {
            "label": reference["name"],
            "nominal": nominal,
            "cars": cars,
            "source_note": "Capacidades y parámetros didácticos salvo los datos de la ficha.",
            "provenance": "Supuesto de ingeniería",
        },
        "line": {
            "name": f"{system.upper()} · Demostración",
            "length_km": length,
            "speed_kmh": speed,
            "headway_min": headway,
            "nominal": nominal,
            "demand": demand,
            "load_factor": 0.85,
            "min_headway_s": 35,
            "reserve_percent": 10,
            "availability": 0.90,
            "terminal_min": 4,
            "intermediate": 4,
            "stop_positions": 1,
            "exchange": "Compartida",
            "board": 4,
            "alight": 3,
            "stop_clearance_s": 10,
            "movement_penalty_s": 7,
            "headways_observed": "4;5;4.5;5.5",
            "random_arrivals": True,
        },
        "doors": [list(door.values()) for door in doors],
    }


def demonstration(index):
    road = _line("rtp", "access", 8, 24, 4.5, 85, 650, 1, 2)
    road["stations"] = [
        [
            ["Terminal A", 0, 32, 0, 0, 27, 1, 8, 2000, "sí"],
            ["Intermedia", 3, 26, 9, 22, "", 1, 8, 1000, "sí"],
            ["Terminal B", 8, 0, 49, 27, 32, 1, 8, 2000, "sí"],
        ],
        [
            ["Terminal B", 0, 25, 0, 0, 24, 1, 8, 2000, "sí"],
            ["Intermedia", 4, 19, 8, 21, "", 1, 8, 1000, "sí"],
            ["Terminal A", 8, 0, 36, 25, 30, 1, 8, 2000, "sí"],
        ],
    ]
    if index == 1:
        road = _line("brt", "volvo7300a", 16, 31, 2.2, 160, 3020, 1, 4)
        road["line"].update(intermediate=12, stop_positions=2, board=18, alight=14)
    elif index == 2:
        road = _line("metro", "nm02", 19, 46, 3, 1530, 21_000, 9, 36)
        road["line"].update(intermediate=15, min_headway_s=100, board=180, alight=120)
    elif index == 3:
        road = _line("cable", "gd10d", 8, 19.8, 0, 10, 1600, 1, 0)
        road["line"].update(
            cable_spacing_m=71.5,
            cable_min_spacing_m=65,
            cable_circuit_km=16.4,
            cable_station_s=12,
            cable_station_limit=2700,
            intermediate=3,
            min_headway_s=11,
            terminal_min=0.5,
        )
    elif index == 4:
        road = _line("combi", "urvan", 5, 20, 7.5, 14, 70, 1, 1)
    if index == 5:
        f = {
            "demand": 2300,
            "growth": 15,
            "grade": 5,
            "budget": 120,
            "radius": 20,
            "width": 10,
            "infra": "Calle;Carril confinado",
            "method": "TOPSIS",
            "w1": 4,
            "w2": 3,
            "w3": 2,
            "w4": 1,
        }
        candidates = [
            ["Autobús", 1900, 20, 22, 5, 10, 12, 5, "Calle", "Supuesto didáctico"],
            ["BRT", 4700, 80, 32, 8, 7, 16, 8, "Carril confinado", "Supuesto didáctico"],
            ["Tren Ligero", 7000, 180, 35, 8, 4, 24, 9, "Vía ligera", "Supuesto didáctico"],
        ]
        return {"mode": 2, "recommend": {"form": f, "candidates": candidates}}
    if index == 6:
        flows = [250, 430, 590, 740, 890, 1000, 1160, 1400, 1560, 1740, 1890]
        observations = [
            [
                q,
                round(9 * (1 + 0.20 * (q / 1800) ** 4), 5),
                "validación" if i in (4, 7, 9) else "ajuste",
            ]
            for i, q in enumerate(flows)
        ]
        return {
            "mode": 1,
            "line": road,
            "integral_tab": 1,
            "advanced": {
                "tab": 0,
                "road": {
                    "form": {
                        "model": "BPR",
                        "capacity": 1800,
                        "fixed_t0": True,
                        "t0": 9,
                        "compare": True,
                    },
                    "observations": observations,
                },
            },
        }
    return {"mode": 1, "line": road}
