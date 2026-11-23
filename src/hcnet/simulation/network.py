"""Traduce una intersección aislada de HCNet a archivos de SUMO."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from math import cos, floor, isclose, radians, sin
from pathlib import Path
from random import Random
from xml.etree import ElementTree as ET

from hcnet.domain.calculations import calculate_intersection
from hcnet.domain.models import IntersectionProject, MovementInput, SignalOptimizationResult
from hcnet.domain.signals import (
    compatible_assignment,
    incompatible_groups,
    prepare_project,
    timeline,
)
from hcnet.simulation.options import FleetType, SimulationOptions


@dataclass(frozen=True, slots=True)
class Route:
    origin: str
    destination: str
    lanes: tuple[int, ...]
    rate: float
    heavy_share: float


@dataclass(slots=True)
class Network:
    program: SignalOptimizationResult
    routes: list[Route]
    links: dict[tuple[str, str, int], tuple[int, str]]
    lanes: dict[str, tuple[str, int, float]]


def write_xml(path: Path, root: ET.Element) -> None:
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def write_network(project: IntersectionProject, directory: Path) -> Network:
    calculate_intersection(project)
    project = prepare_project(project)
    if not compatible_assignment(project.lane_groups, incompatible_groups(project)):
        raise ValueError("Hay movimientos protegidos incompatibles en la misma fase.")
    program = timeline(project)
    if program is None or not isclose(
        program.phases[-1].end_s, program.cycle_length_s, abs_tol=0.01
    ):
        raise ValueError("SUMO requiere un programa completo de verdes, amarillos y todo rojo.")
    if any(p.green_s <= 0 or p.yellow_s <= 0 or p.all_red_s < 0 for p in program.phases):
        raise ValueError("El programa semafórico contiene intervalos no representables.")
    if not {g.signal_phase for g in project.lane_groups} <= {
        p.phase_number for p in program.phases
    }:
        raise ValueError("Hay movimientos sin una fase válida.")
    branches = project.active_branches
    if any(
        abs((a.azimuth - b.azimuth + 180) % 360 - 180) < 10 for a, b in combinations(branches, 2)
    ):
        raise ValueError("Los ejes de dos ramales están demasiado próximos para generar la red.")
    ids = {branch.code: str(index) for index, branch in enumerate(branches)}
    inbound = {branch.code: branch.inbound_lanes for branch in branches}
    outbound = {branch.code: branch.outbound_lanes for branch in branches}
    nodes, edges, turns = (ET.Element(tag) for tag in ("nodes", "edges", "connections"))
    ET.SubElement(nodes, "node", id="J", x="0", y="0", type="traffic_light")
    lanes = {}
    routes = []
    links = {}
    for branch in branches:
        groups = [g for g in project.lane_groups if g.origin_branch == branch.code]
        if len({g.approach_length_m for g in groups}) > 1:
            raise ValueError(f"Ramal {branch.code}: define una longitud común para sus carriles.")
        length = groups[0].approach_length_m if groups else 150.0
        speed = groups[0].free_flow_speed_kmh / 3.6 if groups else 40 / 3.6
        angle = radians(branch.azimuth)
        # El borde exterior se separa del cruce; el atributo length fija la longitud simulada.
        radius = length + 40
        code = ids[branch.code]
        ET.SubElement(
            nodes,
            "node",
            id=f"n{code}",
            x=str(radius * sin(angle)),
            y=str(radius * cos(angle)),
            type="dead_end",
        )
        edge = ET.SubElement(
            edges,
            "edge",
            {
                "id": f"i{code}",
                "from": f"n{code}",
                "to": "J",
                "length": str(length),
                "numLanes": str(inbound[branch.code]),
                "speed": str(speed),
            },
        )
        ET.SubElement(
            edges,
            "edge",
            {
                "id": f"o{code}",
                "from": "J",
                "to": f"n{code}",
                "length": str(length),
                "numLanes": str(outbound[branch.code]),
                "speed": str(speed),
            },
        )
        for lane in range(1, inbound[branch.code] + 1):
            uses = [g for g in groups if lane in g.lane_indices]
            geometry = {(g.free_flow_speed_kmh, g.lane_width_m) for g in uses}
            if len(geometry) > 1:
                raise ValueError(f"Ramal {branch.code}, carril {lane}: geometría contradictoria.")
            if uses:
                lane_speed, width = geometry.pop()
                ET.SubElement(
                    edge, "lane", index=str(lane - 1), speed=str(lane_speed / 3.6), width=str(width)
                )
            lanes[f"i{code}_{lane - 1}"] = (branch.code, lane, length)

        for group in groups:
            movements = [m for m in group.movements if m.enabled]
            if not movements:
                if len(group.destination_branches) != 1:
                    raise ValueError(f"{group.label}: captura los aforos por destino para simular.")
                movements = [
                    MovementInput(
                        group.destination_branches[0],
                        group.volume_veh_h,
                        group.peak_hour_factor,
                        group.heavy_vehicles_percent,
                    )
                ]
            for move in movements:
                dest = f"o{ids[move.destination]}"
                route = Route(
                    f"i{code}",
                    dest,
                    group.lane_indices,
                    move.volume / move.phf,
                    move.heavy_percent / 100,
                )
                routes.append(route)
                for lane in route.lanes:
                    link = (route.origin, route.destination, lane - 1)
                    if link in links:
                        raise ValueError(
                            f"{group.label}: un giro se asignó dos veces al mismo carril."
                        )
                    links[link] = (
                        group.signal_phase,
                        "g" if move.operation == "Permisivo" else "G",
                    )
                    ET.SubElement(
                        turns,
                        "connection",
                        {
                            "from": route.origin,
                            "to": route.destination,
                            "fromLane": str(lane - 1),
                            "toLane": str(min(lane, outbound[move.destination]) - 1),
                        },
                    )
    for name, root in (("nodes", nodes), ("edges", edges), ("turns", turns)):
        write_xml(directory / f"{name}.xml", root)
    return Network(program, routes, links, lanes)


def install_program(path: Path, network: Network) -> None:
    root = ET.parse(path).getroot()
    controllers = root.findall("tlLogic")
    if len(controllers) != 1 or controllers[0].get("id") != "J":
        raise ValueError("La red generada no contiene el semáforo central esperado.")
    controller = controllers[0]
    controller[:] = []
    controller.set("offset", "0")
    indexed = {}
    found = set()
    for c in root.findall("connection"):
        if c.get("tl") != "J":
            continue
        key = (c.attrib["from"], c.attrib["to"], int(c.attrib["fromLane"]))
        index = int(c.attrib["linkIndex"])
        if key not in network.links or index in indexed:
            raise ValueError("SUMO generó conexiones semafóricas distintas de los movimientos.")
        indexed[index] = network.links[key]
        found.add(key)
    if found != set(network.links) or set(indexed) != set(range(len(indexed))):
        raise ValueError("SUMO no conservó todas las conexiones semafóricas solicitadas.")
    for phase in network.program.phases:
        for duration, signal in (
            (phase.green_s, "green"),
            (phase.yellow_s, "yellow"),
            (phase.all_red_s, "all-red"),
        ):
            if duration == 0:
                continue
            state = "".join(
                ("y" if signal == "yellow" else indexed[i][1])
                if indexed[i][0] == phase.phase_number and signal != "all-red"
                else "r"
                for i in range(len(indexed))
            )
            ET.SubElement(controller, "phase", duration=f"{duration:.9f}", state=state)
    write_xml(path, root)


def write_demand(
    path: Path,
    network: Network,
    options: SimulationOptions,
    fleet: tuple[FleetType, ...],
    seed: int,
) -> int:
    rng = Random(seed)
    root = ET.Element("routes")
    categories = defaultdict(list)
    for i, item in enumerate(fleet):
        if not item.percent:
            continue
        type_id = f"v{i}"
        categories[item.category].append((type_id, item.percent))
        ET.SubElement(
            root,
            "vType",
            id=type_id,
            vClass=item.vclass,
            emissionClass=item.emission_class,
            tau=str(options.tau),
            minGap=str(options.min_gap),
            accel=str(options.accel),
            decel=str(options.decel),
            lcStrategic=str(options.strategic),
        )
    total = options.duration + options.warmup
    expected = [row.rate * total / 3600 for row in network.routes]
    if sum(expected) > 200_000:
        raise ValueError("El periodo y la demanda superan 200 000 vehículos por corrida.")
    counts = [floor(value) for value in expected]
    order = sorted(range(len(counts)), key=lambda i: counts[i] - expected[i])
    for i in order[: round(sum(expected)) - sum(counts)]:
        counts[i] += 1
    vehicles = []
    for i, (route, count) in enumerate(zip(network.routes, counts, strict=True)):
        if count == 0:
            continue
        route_id = f"r{i}"
        ET.SubElement(root, "route", id=route_id, edges=f"{route.origin} {route.destination}")
        # Se mantiene la mezcla pesada de cada movimiento, con redondeo al vehículo más cercano.
        heavy = [True] * round(count * route.heavy_share)
        heavy += [False] * (count - len(heavy))
        rng.shuffle(heavy)
        for j, is_heavy in enumerate(heavy):
            types, weights = zip(*categories["pesado" if is_heavy else "ligero"], strict=True)
            type_id = rng.choices(types, weights, k=1)[0]
            depart = (j + rng.random()) * total / count
            vehicles.append((depart, route_id, type_id, route.lanes[j % len(route.lanes)] - 1))
    for i, (depart, route_id, type_id, lane) in enumerate(sorted(vehicles)):
        ET.SubElement(
            root,
            "vehicle",
            id=f"veh{i}",
            route=route_id,
            type=type_id,
            depart=f"{min(depart, total - 0.001):.3f}",
            departLane=str(lane),
        )
    if not vehicles:
        raise ValueError("La demanda y duración no producen vehículos para simular.")
    write_xml(path, root)
    return len(vehicles)
