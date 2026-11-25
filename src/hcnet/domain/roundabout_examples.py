"""Casos hipotéticos seleccionables de ingeniería de rotondas."""

import json
from dataclasses import replace

from hcnet.domain.roundabout_engineering import Movement, Site, blank_arms
from hcnet.domain.roundabout_planning import import_intersection
from hcnet.domain.sample import demonstration_project

EXAMPLES = (
    "Cuatro ramales, un carril",
    "Dos carriles y reparto de movimientos",
    "Accesos asimétricos en tres ramales",
    "Predimensionamiento con diámetro fijo",
    "Comparación HCM, brechas, lineal y Kimber",
    "Calibración con descarga observada",
    "Conversión desde una intersección semaforizada",
    "Corridas vehiculares con SUMO",
    "Conversión no recomendable por falta de espacio",
)


def example(index):
    arms = tuple(
        replace(
            a,
            entry=4.5,
            exit=4.5,
            approach=3.5,
            flare=14,
            entry_angle=28,
            curb_radius=18,
            entry_path=22,
            exit_path=35,
            length=140,
            speed=40,
            storage=55,
            splitter=2,
            sight=45,
        )
        for a in blank_arms()
    )
    demand = tuple(
        Movement(a, b, v, heavy=6, bus=2, phf=0.92, source="Aforo hipotético")
        for a, b, v in (
            ("A", "C", 405),
            ("A", "D", 100),
            ("B", "A", 210),
            ("B", "D", 180),
            ("C", "A", 390),
            ("C", "B", 130),
            ("D", "B", 165),
            ("D", "C", 120),
        )
    )
    site = Site(
        name=EXAMPLES[index], arms=arms, movements=demand, diameter=40, width=5, apron=1.3, speed=30
    )
    settings = {"mode": 0}
    if index == 1:
        site = replace(
            site,
            kind="Dos carriles",
            lanes=2,
            diameter=51,
            width=9,
            arms=tuple(replace(a, inbound=2, outbound=2, entry=8, exit=8) for a in arms),
            movements=tuple(
                replace(m, lane2=45 if ((ord(m.origin) - ord(m.destination)) % 4 >= 2) else 0)
                for m in demand
            ),
        )
    elif index == 2:
        site = replace(
            site,
            arms=(arms[0], replace(arms[1], azimuth=115), replace(arms[2], azimuth=238)),
            movements=tuple(m for m in demand if "D" not in (m.origin, m.destination)),
        )
    elif index == 3:
        site = replace(
            site,
            diameter=42,
            width=0,
            locks=("diameter",),
            available_diameter=49,
            vehicle_name="Autobús urbano",
            vehicle_width=2.55,
            minimum_turn=12,
        )
        settings = {"mode": 1, "advanced": True, "tab": 2}
    elif index == 4:
        site = replace(
            site,
            critical_gap=4.8,
            followup=2.7,
            linear_a=1420,
            linear_b=0.65,
            linear_min=0,
            linear_max=1600,
            model_source="Valores sintéticos didácticos",
            hybrid=True,
        )
        settings = {"advanced": True, "tab": 2}
    elif index == 5:
        counts = [
            [q, round(1430 * (0.9991**q), 1), "ajuste" if i % 3 != 2 else "validación"]
            for i, q in enumerate((200, 300, 400, 500, 600, 700, 800, 900, 1100))
        ]
        settings = {"advanced": True, "tab": 4, "calibration": {"counts": counts}}
    elif index in (6, 8):
        from hcnet.domain.models import IntersectionProject

        project = demonstration_project()
        site = replace(
            import_intersection(project),
            name=EXAMPLES[index],
            speed=30,
            available_diameter=60 if index == 6 else 17,
        )
        physical = {b.code: b for b in project.active_branches}
        archived = replace(
            site,
            arms=tuple(
                replace(
                    a,
                    inbound=physical[a.code].inbound_lanes,
                    outbound=physical[a.code].outbound_lanes,
                )
                for a in site.arms
            ),
        )
        assert isinstance(project, IntersectionProject)
        settings = {
            "mode": 3,
            "tab": 3,
            "original": json.loads(json.dumps(project.to_dict())),
            "original_site": archived.to_dict(),
        }
    elif index == 7:
        settings = {
            "advanced": True,
            "tab": 5,
            "simulation": {"form": {"warmup": 30, "runs": 3, "duration": 150}},
        }
    return site, settings
