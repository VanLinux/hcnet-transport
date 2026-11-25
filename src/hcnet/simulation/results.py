"""Lectura de las salidas de SUMO y estadísticas del periodo de medición."""

import base64
import gzip
import json
import zlib
from collections import defaultdict
from contextlib import contextmanager
from math import ceil, sqrt
from pathlib import Path
from statistics import mean, stdev
from xml.etree import ElementTree as ET

from hcnet.simulation.options import POLLUTANTS

T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201)
TRIP_FIELDS = {
    "Demora SUMO (timeLoss), s": "timeLoss",
    "Duración de viaje, s": "duration",
    "Espera (<0.1 m/s), s": "waitingTime",
    "Paradas por viaje (episodios)": "waitingCount",
}


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "ci95": None}
    count = len(values)
    average = mean(values)
    deviation = stdev(values) if count > 1 else None
    margin = (
        T95[min(count - 2, len(T95) - 1)] * deviation / sqrt(count)
        if deviation is not None
        else None
    )
    return {
        "n": count,
        "mean": average,
        "sd": deviation,
        "ci95": ([average - margin, average + margin] if margin is not None else None),
    }


def queue_stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {"mean": mean(values), "max": max(values), "p95": ordered[ceil(0.95 * len(values)) - 1]}


def pack(series: list) -> str:
    return base64.b64encode(
        zlib.compress(json.dumps(series, separators=(",", ":")).encode())
    ).decode()


def unpack(payload: str) -> list:
    decoded = zlib.decompressobj()
    try:
        raw = decoded.decompress(base64.b64decode(payload, validate=True), 30_000_000)
    except zlib.error as exc:
        raise ValueError("Serie temporal dañada.") from exc
    if not decoded.eof:
        raise ValueError("La serie temporal está incompleta o supera el límite de lectura.")
    return json.loads(raw)


def output_rows(path: Path, name: str):
    with gzip.open(path, "rb") as stream:
        reader = ET.iterparse(stream, events=("start", "end"))
        _, root = next(reader)
        for event, element in reader:
            if event == "end" and element.tag == name:
                yield element
                root.clear()


@contextmanager
def cancellable_rows(path: Path, tag: str):
    rows = output_rows(path, tag)
    try:
        yield rows
    finally:
        rows.close()


def parse_run(
    directory: Path,
    network,
    options,
    planned: int,
    seed: int,
    check,
    *,
    signals=True,
    hydrocarbons=False,
) -> dict:
    pollutants = POLLUTANTS | {"HC": "g"} if hydrocarbons else POLLUTANTS
    fields = defaultdict(list)
    measurement_start, end = options.warmup, options.warmup + options.duration
    departed = arrived = cohort = completed = stopped_trips = 0
    with cancellable_rows(directory / "trips.xml.gz", "tripinfo") as trips:
        for trip in trips:
            check()
            depart, arrival = float(trip.get("depart", "-1")), float(trip.get("arrival", "-1"))
            departed += depart >= 0
            arrived += arrival >= 0
            if depart < measurement_start or depart >= end:
                continue
            cohort += 1
            if arrival < 0 or arrival >= end:
                continue
            completed += 1
            for label, field in TRIP_FIELDS.items():
                fields[label].append(float(trip.attrib[field]))
            duration = float(trip.attrib["duration"])
            if duration > 0:
                fields["Velocidad media por viaje, km/h"].append(
                    3.6 * float(trip.attrib["routeLength"]) / duration
                )
            stopped_trips += float(trip.attrib["waitingCount"]) > 0

    indexed = {lane: i for i, lane in enumerate(network.lanes)}
    queue = [[0.0] * len(indexed) for _ in range(options.duration)]
    frames = set()
    with cancellable_rows(directory / "queues.xml.gz", "data") as samples:
        for sample in samples:
            check()
            index = round(float(sample.attrib["timestep"])) - measurement_start
            if not 0 <= index < options.duration:
                continue
            frames.add(index)
            for lane in sample.iter("lane"):
                if lane.attrib["id"] in indexed:
                    queue[index][indexed[lane.attrib["id"]]] = float(lane.attrib["queueing_length"])
    if len(frames) != options.duration:
        raise ValueError("SUMO no devolvió la serie completa de colas para el periodo medido.")

    emissions = [[0.0] * len(pollutants) for _ in range(options.duration)]
    by_type = defaultdict(lambda: [0.0] * len(pollutants))
    stopped = [[0] * len(indexed) for _ in range(options.duration)]
    in_queue = [[0] * len(indexed) for _ in range(options.duration)]
    frames.clear()
    with cancellable_rows(directory / "emissions.xml.gz", "timestep") as samples:
        for sample in samples:
            check()
            index = round(float(sample.attrib["time"])) - measurement_start
            if not 0 <= index < options.duration:
                continue
            frames.add(index)
            for vehicle in sample.iter("vehicle"):
                a = vehicle.attrib
                amounts = [
                    float(a[key])
                    / (1_000_000 if key == "CO2" else 1 if key == "electricity" else 1000)
                    for key in pollutants
                ]  # Paso de integración de 1 s.
                for i, amount in enumerate(amounts):
                    emissions[index][i] += amount
                    by_type[a["type"]][i] += amount
                if a.get("lane") in indexed and float(a["speed"]) < 0.1:
                    lane = a["lane"]
                    lane_index = indexed[lane]
                    stopped[index][lane_index] += 1
                    extent = queue[index][lane_index]
                    if extent > 0 and network.lanes[lane][2] - float(a["pos"]) <= extent + 0.1:
                        in_queue[index][lane_index] += 1
    if len(frames) != options.duration:
        raise ValueError("SUMO no devolvió la serie completa de emisiones para el periodo medido.")

    signal = [None] * options.duration
    if signals:
        phase_numbers = [
            phase.phase_number
            for phase in network.program.phases
            for seconds in (phase.green_s, phase.yellow_s, phase.all_red_s)
            if seconds > 0
        ]
        with cancellable_rows(directory / "signals.xml.gz", "tlsState") as samples:
            for sample in samples:
                check()
                index = round(float(sample.attrib["time"])) - measurement_start
                if 0 <= index < options.duration:
                    signal[index] = [
                        phase_numbers[int(sample.attrib["phase"])],
                        sample.attrib["state"],
                    ]
        if any(item is None for item in signal):
            raise ValueError("SUMO no devolvió los estados del semáforo para el periodo medido.")

    lane_stats = {
        lane: queue_stats([row[index] for row in queue]) for lane, index in indexed.items()
    }
    branch_lanes = defaultdict(list)
    for i, (branch, _, _) in enumerate(network.lanes.values()):
        branch_lanes[branch].append(i)
    branch_stats = {
        branch: queue_stats([max(row[i] for i in indices) for row in queue])
        for branch, indices in branch_lanes.items()
    }
    global_queue = queue_stats([max(row) for row in queue])
    metrics = {k: mean(v) for k, v in fields.items()}
    metrics.update(
        {
            "Cola media · extensión máxima instantánea, m": global_queue["mean"],
            "Cola máxima · extensión máxima instantánea, m": global_queue["max"],
            "Cola P95 · extensión máxima instantánea, m": global_queue["p95"],
            "Vehículos detenidos (viajes completos)": stopped_trips,
            "Detenidos dentro de la cola · media instantánea": mean(map(sum, in_queue)),
            "Vehículos por insertar al cierre": planned - departed,
            "Vehículos en red al cierre": departed - arrived,
        }
    )
    return {
        "seed": seed,
        "planned": planned,
        "departed": departed,
        "arrived": arrived,
        "cohort": cohort,
        "completed": completed,
        "metrics": metrics,
        "lanes": lane_stats,
        "branches": branch_stats,
        "signal_series": pack(signal),
        "queue_series": pack(queue),
        "stopped_series": pack(stopped),
        "in_queue_series": pack(in_queue),
        "emissions": dict(zip(pollutants, map(sum, zip(*emissions, strict=True)), strict=True)),
        "by_type": {k: dict(zip(pollutants, v, strict=True)) for k, v in by_type.items()},
        "emission_series": pack([[round(value, 10) for value in row] for row in emissions]),
    }
