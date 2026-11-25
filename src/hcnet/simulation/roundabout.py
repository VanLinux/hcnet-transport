"""Generación de una rotonda de prioridad y experimentos de demanda común con SUMO."""

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from math import radians
from pathlib import Path
from random import Random
from secrets import randbelow
from shutil import copy2
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from hcnet.domain.roundabout_engineering import design_geometry, network, order, point, separated
from hcnet.domain.roundabout_planning import import_intersection, same_demand
from hcnet.simulation.network import install_program, write_network, write_xml
from hcnet.simulation.options import DEFAULT_FLEET
from hcnet.simulation.results import parse_run, stats, unpack
from hcnet.simulation.runner import SimulationCancelled, _command


@dataclass
class RoundNetwork:
    lanes: dict
    paths: dict
    entries: set
    ring: set
    merges: list


def _xyz(pos):
    return f"{pos[0]:.6f},{pos[1]:.6f}"


def write_round_network(site, directory):
    routes = network(site)
    geom = design_geometry(site)
    if site.kind in ("Minirotonda", "Turborrotonda", "Multicarril") or site.lanes > 2:
        raise ValueError("SUMO requiere una geometría convencional sin isla transitable.")
    if geom["limit_issues"]:
        raise ValueError("Resuelve las restricciones de espacio antes de simular.")
    arms = order(site)
    if any(a.bypass_width or a.inbound > 2 or a.outbound > 2 for a in arms):
        raise ValueError("SUMO no tiene un modelo de estos carriles segregados o múltiples.")
    if any(not a.length or not a.speed for a in arms) or not site.speed:
        raise ValueError("Captura longitud y velocidad de cada ramal y velocidad del anillo.")
    rad = geom["centerline"]
    if not separated(site, rad, geom["lane_width"]):
        raise ValueError("Los ramales no conservan separación física suficiente para la red SUMO.")
    definitions = [ET.Element(name) for name in ("nodes", "edges", "connections")]
    nodes, edges, connections = definitions
    lanes, paths, entries, rings, merges = {}, {}, set(), set(), []
    sign = -1 if site.direction == "Antihorario" else 1

    def connect(before, after, source, target, priority=False):
        params = {"from": before, "to": after, "fromLane": str(source), "toLane": str(target)}
        if priority:
            params["pass"] = "true"
        ET.SubElement(connections, "connection", params)

    def add_node(name, azimuth, radius, kind="priority"):
        x, y = point(azimuth, radius)
        ET.SubElement(nodes, "node", id=name, x=str(x), y=str(y), type=kind)

    def edge(identifier, start, end, count, speed, width, priority, length, shape=""):
        attrib = {
            "id": identifier,
            "from": start,
            "to": end,
            "numLanes": str(count),
            "speed": str(speed / 3.6),
            "priority": str(priority),
            "width": str(width),
            "length": str(length),
            "spreadType": "center",
        }
        if shape:
            attrib["shape"] = shape
        ET.SubElement(edges, "edge", attrib)

    for i, arm in enumerate(arms):
        code = arm.code
        n = arms[(i + 1) % len(arms)]
        arc = (sign * (n.azimuth - arm.azimuth)) % 360
        # Una divergencia y una convergencia distintas por ramal evitan excluir
        # de los conflictos el flujo que se incorpora después del punto de salida.
        spread = min(7.0, arc / 5, (sign * (arm.azimuth - arms[i - 1].azimuth)) % 360 / 5)
        next_arc = (sign * (arms[(i + 2) % len(arms)].azimuth - n.azimuth)) % 360
        next_spread = min(7.0, arc / 5, next_arc / 5)
        incoming = f"in{code}"
        outgoing = f"out{code}"
        leave = f"d{code}"
        join = f"m{code}"
        short = f"s{code}"
        long = f"r{code}"
        previous = f"r{arms[i - 1].code}"
        add_node(leave, arm.azimuth - sign * spread, rad)
        add_node(join, arm.azimuth + sign * spread, rad)
        add_node(f"x{code}", arm.azimuth, rad + arm.length, "dead_end")
        if arm.inbound:
            edge(
                incoming,
                f"x{code}",
                join,
                arm.inbound,
                arm.speed,
                arm.entry / arm.inbound if arm.entry else geom["lane_width"],
                1,
                arm.length,
            )
            entries.add(incoming)
            for j in range(arm.inbound):
                lanes[f"{incoming}_{j}"] = (code, j + 1, arm.length)
                connect(incoming, long, j, min(j, site.lanes - 1))
                merges.append((incoming, long, j, short, min(j, site.lanes - 1), join))
        if arm.outbound:
            edge(
                outgoing,
                leave,
                f"x{code}",
                arm.outbound,
                arm.speed,
                arm.exit / arm.outbound if arm.exit else geom["lane_width"],
                1,
                arm.length,
            )
        for identifier, src, target, start, extent in (
            (short, leave, join, arm.azimuth - sign * spread, 2 * spread),
            (long, join, f"d{n.code}", arm.azimuth + sign * spread, arc - spread - next_spread),
        ):
            rings.add(identifier)
            samples = max(2, round(extent / 8))
            shape = " ".join(
                _xyz(point(start + sign * extent * j / samples, rad)) for j in range(samples + 1)
            )
            edge(
                identifier,
                src,
                target,
                site.lanes,
                site.speed,
                geom["lane_width"],
                4,
                rad * radians(extent),
                shape,
            )
        for j in range(site.lanes):
            connect(previous, short, j, j)
            connect(short, long, j, j, priority=True)
            if arm.outbound and j < arm.outbound:
                connect(previous, outgoing, j, j)
    ET.SubElement(
        edges,
        "roundabout",
        edges=" ".join(edge for a in arms for edge in (f"s{a.code}", f"r{a.code}")),
    )
    for route in routes:
        start, end = route["od"]
        lane = route["lane"] - 1
        ring = route["segment"]
        if not route["rate"]:
            continue
        if route["ring_lane"] > 1 and by_outer_crossing(routes, end):
            raise ValueError(
                f"{end}. La salida interior cruza un flujo exterior continuo; "
                "requiere revisar y modelar la canalización específica."
            )
        path = [f"in{start}", f"r{ring[0]}"]
        for c in ring[1:]:
            path.extend((f"s{c}", f"r{c}"))
        path.append(f"out{end}")
        paths.setdefault((start, end), []).append((path, lane, route["rate"]))
    for filename, root in zip(("nodes.xml", "edges.xml", "turns.xml"), definitions, strict=True):
        write_xml(directory / filename, root)
    return RoundNetwork(lanes, paths, entries, rings, merges)


def by_outer_crossing(routes, arm):
    return any(r["ring_lane"] == 1 and r["rate"] > 0 and arm in r["segment"][1:] for r in routes)


def verify_round_network(path, roundnet):
    """netconvert debe conservar el anillo y ceder paso al flujo circulante en cada fusión."""
    root = ET.parse(path).getroot()
    turns = {
        (c.get("from"), c.get("to"), int(c.get("fromLane", 0)), int(c.get("toLane", 0))): c
        for c in root.findall("connection")
    }
    if not any(
        set(r.get("edges", "").split()) == roundnet.ring for r in root.findall("roundabout")
    ):
        raise ValueError("netconvert no conservó el anillo declarado.")
    for inbound, outgoing, lane, circulating, ring_lane, join in roundnet.merges:
        entry = next(
            (c for (a, b, i, _), c in turns.items() if (a, b, i) == (inbound, outgoing, lane)), None
        )
        ring = turns.get((circulating, outgoing, ring_lane, ring_lane))
        # Los bitsets internos de SUMO se verifican con orden intLanes del nodo.
        junction = root.find(f"./junction[@id='{join}']")
        if entry is None or ring is None or junction is None:
            raise ValueError(f"{join}. SUMO perdió una conexión de acceso.")
        vias = junction.get("intLanes", "").split()
        idx = vias.index(entry.attrib["via"])
        priority_idx = vias.index(ring.attrib["via"])
        entry_response = junction.find(f"./request[@index='{idx}']")
        ring_response = junction.find(f"./request[@index='{priority_idx}']")
        if (
            entry_response is None
            or ring_response is None
            or entry_response.attrib["response"][-1 - priority_idx] != "1"
            or ring_response.attrib["response"][-1 - idx] != "0"
        ):
            raise ValueError(f"{join}. SUMO no verificó la cesión al carril circulante.")
    return turns


def _schedule(site, options, seed):
    """Demandas OD iguales entre escenarios, redondeadas una vez por corrida."""
    rng = Random(seed)
    period = options.duration + options.warmup
    demands = sorted(
        (m for m in site.movements if m.enabled and m.volume),
        key=lambda m: (m.origin, m.destination),
    )
    expected = [m.volume / m.phf * period / 3600 for m in demands]
    if sum(expected) > 200_000:
        raise ValueError("La demanda supera 200 000 vehículos por corrida.")
    counts = [int(x) for x in expected]
    excess = round(sum(expected)) - sum(counts)
    largest = sorted(range(len(counts)), key=lambda i: expected[i] - counts[i], reverse=True)
    for i in largest[:excess]:
        counts[i] += 1
    vehicles = []
    for m, count in zip(demands, counts, strict=True):
        for i in range(count):
            depart = min((i + rng.random()) * period / count, period - 0.001)
            weights = (100 - m.heavy - m.bus - m.motorcycle, m.heavy, m.bus, m.motorcycle)
            kind = rng.choices(("light", "heavy", "bus", "moto"), weights, k=1)[0]
            vehicles.append((depart, (m.origin, m.destination), kind, rng.random()))
    if not vehicles:
        raise ValueError("La demanda solicitada no produce vehículos para esta corrida.")
    return sorted(vehicles)


MIX = {
    "light": DEFAULT_FLEET[0],
    "heavy": DEFAULT_FLEET[4],
    "bus": DEFAULT_FLEET[6],
    "moto": DEFAULT_FLEET[0],
}


def write_round_demand(path, paths, schedule, options, *, classes=None, lock_lanes=True):
    attributes = classes or {}
    root = ET.Element("routes")
    for kind, vehicle in MIX.items():
        ET.SubElement(
            root,
            "vType",
            id=kind,
            vClass="motorcycle" if kind == "moto" else vehicle.vclass,
            emissionClass=str(attributes.get(kind) or vehicle.emission_class),
            tau=str(options.tau),
            minGap=str(options.min_gap),
            accel=str(options.accel),
            decel=str(options.decel),
            lcStrategic=str(options.strategic),
            **(
                {"lcKeepRight": "0", "lcSpeedGain": "0", "lcCooperative": "0"} if lock_lanes else {}
            ),
        )
    ids = {}
    for od, variants in paths.items():
        for index, (edges, lane, rate) in enumerate(variants):
            route_id = f"r{od[0]}{od[1]}_{index}"
            ET.SubElement(root, "route", id=route_id, edges=" ".join(edges))
            ids.setdefault(od, []).append((route_id, lane, rate))
    for i, (depart, od, kind, draw) in enumerate(schedule):
        if od not in ids:
            raise ValueError(f"El movimiento {od[0]} → {od[1]} no tiene conexión en el escenario.")
        choices = ids[od]
        target = sum(x[2] for x in choices) * draw
        selected = choices[-1]
        for choice in choices:
            target -= choice[2]
            if target <= 0:
                selected = choice
                break
        route_id, lane, _ = selected
        ET.SubElement(
            root,
            "vehicle",
            id=f"veh{i}",
            route=route_id,
            depart=f"{depart:.3f}",
            type=kind,
            departLane=str(lane),
        )
    write_xml(path, root)


def _summary(runs):
    names = dict.fromkeys(name for row in runs for name in row["metrics"])
    return {
        "metrics": {
            key: stats([r["metrics"][key] for r in runs if key in r["metrics"]]) for key in names
        },
        "emissions": {
            key: stats([r["emissions"][key] for r in runs]) for key in runs[0]["emissions"]
        },
        "runs": runs,
    }


def simulate_roundabouts(
    scenarios,
    options,
    binaries,
    cancel,
    *,
    progress=lambda *_: None,
    original=None,
    archive=None,
    classes=None,
):
    options.validate()
    if not scenarios:
        raise ValueError("Selecciona al menos una rotonda para simular.")
    reference = scenarios[0][1]
    network(reference)
    if any(not same_demand(reference, site) for _, site in scenarios[1:]) or (
        original is not None and not same_demand(reference, import_intersection(original))
    ):
        raise ValueError("Compara sólo escenarios con el mismo aforo OD, FHMD y composición.")

    def check():
        if cancel.is_set():
            raise SimulationCancelled()

    first = options.seed if options.seed is not None else randbelow(2_147_483_630)
    seeds = list(range(first, first + options.runs))
    schedules = [_schedule(reference, options, seed) for seed in seeds]
    executable, netconvert = map(str, binaries)
    results = []
    specs = list(scenarios)
    if original is not None:
        specs.insert(0, ("Original semaforizado", None))
    with TemporaryDirectory(prefix="hcnet-round-") as folder:
        root = Path(folder)
        version = _command([executable, "--version"], root, cancel).splitlines()[0]
        number = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
        if number is None or tuple(map(int, number.groups())) < (1, 14, 0):
            raise ValueError("Se requiere SUMO 1.14 o posterior para las unidades de combustible.")
        for index, (name, site) in enumerate(specs):
            check()
            directory = root / f"escenario-{index + 1}"
            directory.mkdir()
            if site is None:
                legacy = write_network(original, directory)
                links = {}
                for movement in legacy.routes:
                    start, end = int(movement.origin[1:]), int(movement.destination[1:])
                    key = (original.active_branches[start].code, original.active_branches[end].code)
                    links.setdefault(key, []).extend(
                        (
                            [movement.origin, movement.destination],
                            lane - 1,
                            movement.rate / len(movement.lanes),
                        )
                        for lane in movement.lanes
                    )
                net = RoundNetwork(legacy.lanes, links, set(), set(), [])
            else:
                net = write_round_network(site, directory)
            _command(
                [
                    netconvert,
                    "-n",
                    "nodes.xml",
                    "-e",
                    "edges.xml",
                    "-x",
                    "turns.xml",
                    "--no-turnarounds",
                    "true",
                    "--geometry.remove",
                    "false",
                    "--offset.disable-normalization",
                    "true",
                    "--xml-validation",
                    "never",
                    "--lefthand",
                    str(site is not None and site.driving == "Izquierda").lower(),
                    "-o",
                    "network.net.xml",
                ],
                directory,
                cancel,
            )
            path = directory / "network.net.xml"
            if site is not None:
                verify_round_network(path, net)
            else:
                install_program(path, legacy)
            runs = []
            out = None
            if archive:
                out = Path(archive) / f"escenario-{index + 1}"
                out.mkdir(parents=True, exist_ok=False)
                for source in (
                    path,
                    directory / "nodes.xml",
                    directory / "edges.xml",
                    directory / "turns.xml",
                ):
                    copy2(source, out / source.name)
            for i, (seed, schedule) in enumerate(zip(seeds, schedules, strict=True)):
                check()
                progress(index * options.runs + i + 1, len(specs) * options.runs)
                write_round_demand(
                    directory / "demand.rou.xml",
                    net.paths,
                    schedule,
                    options,
                    classes=classes,
                    lock_lanes=site is not None,
                )
                output = _command(
                    [
                        executable,
                        "-n",
                        "network.net.xml",
                        "-r",
                        "demand.rou.xml",
                        "--xml-validation",
                        "never",
                        "--seed",
                        str(seed),
                        "--step-length",
                        "1",
                        "--end",
                        str(options.duration + options.warmup),
                        "--tripinfo-output",
                        "trips.xml.gz",
                        "--tripinfo-output.write-unfinished",
                        "true",
                        "--queue-output",
                        "queues.xml.gz",
                        "--emission-output",
                        "emissions.xml.gz",
                        "--time-to-teleport",
                        "-1",
                        "--no-step-log",
                        "true",
                    ],
                    directory,
                    cancel,
                )
                run = parse_run(
                    directory,
                    net,
                    options,
                    len(schedule),
                    seed,
                    check,
                    signals=False,
                    hydrocarbons=True,
                )
                planned_period = sum(t >= options.warmup for t, *_ in schedule)
                run["metrics"].update(
                    {
                        "Solicitados en medición": planned_period,
                        "Insertados en medición (por salida efectiva)": run["cohort"],
                        "Viajes completos de la cohorte": run["completed"],
                    }
                )
                queue = unpack(run["queue_series"])
                run["duration_positive_s"] = [
                    sum(row[i] > 0 for row in queue) for i in range(len(net.lanes))
                ]
                run["queue_intervals"] = []
                for j in range(len(net.lanes)):
                    positive = [
                        t for t, values in enumerate(queue, options.warmup) if values[j] > 0
                    ]
                    run["queue_intervals"].append(
                        [
                            positive[0] if positive else None,
                            positive[-1] if positive else None,
                            bool(
                                positive and positive[-1] == options.warmup + options.duration - 1
                            ),
                        ]
                    )
                if run["cohort"]:
                    run["metrics"]["CO2 (g por inserción; normalización de periodo)"] = (
                        run["emissions"]["CO2"] * 1000 / run["cohort"]
                    )
                run["warnings"] = [line for line in output.splitlines() if "Warning:" in line][-12:]
                runs.append(run)
                if out:
                    for artifact in (
                        "demand.rou.xml",
                        "trips.xml.gz",
                        "queues.xml.gz",
                        "emissions.xml.gz",
                    ):
                        copy2(directory / artifact, out / f"{seed}-{artifact}")
            results.append(
                _summary(runs)
                | {
                    "name": name,
                    "lanes": list(map(list, net.lanes.values())),
                    "topology": sha256(path.read_bytes()).hexdigest(),
                    "site": site.to_dict() if site is not None else None,
                }
            )
    check()
    if archive:
        Path(archive, "corridas.json").write_text(
            json.dumps(
                {
                    "sumo": version,
                    "options": asdict(options),
                    "seeds": seeds,
                    "classes": classes or {},
                    "scenarios": [{"name": r["name"], "topology": r["topology"]} for r in results],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return {
        "sumo": version,
        "options": asdict(options),
        "seeds": seeds,
        "scenarios": results,
        "classes": {kind: (classes or {}).get(kind) or v.emission_class for kind, v in MIX.items()},
    }
