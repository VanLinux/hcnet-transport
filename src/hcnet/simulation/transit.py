"""Ejecución de un corredor vial observado y lectura de resultados SUMO."""

from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from hcnet.domain.transit_engineering import service_quality
from hcnet.simulation.network import write_xml
from hcnet.simulation.runner import SimulationCancelled, _command

INPUT_FILES = ("net-file", "route-files", "additional-files")
ALLOWED_OPTIONS = {
    "time": {"begin", "end", "step-length"},
    "processing": {"time-to-teleport", "time-to-teleport.highways", "default.speeddev"},
}


def _copy_configuration(path, destination):
    root = ET.parse(path).getroot()
    if root.tag != "configuration":
        raise ValueError("El archivo debe contener una configuración SUMO.")
    copied = ET.Element("configuration")
    inputs = ET.SubElement(copied, "input")
    digest = sha256(path.read_bytes())
    for tag in INPUT_FILES:
        value = root.findtext(f"input/{tag}") or ""
        item = root.find(f"input/{tag}")
        if item is not None:
            value = item.get("value", value)
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if tag != "additional-files" and not parts:
            raise ValueError("La configuración debe indicar una red y rutas explícitas.")
        if not parts:
            continue
        paths = []
        for name in parts:
            source = (path.parent / name).resolve(strict=True)
            if "," in str(source):
                raise ValueError("Las rutas a los insumos de SUMO no pueden contener comas.")
            with source.open("rb") as stream:
                digest.update(sha256_file(stream))
            if tag == "additional-files":
                # Se excluyen dispositivos y archivos adicionales no compatibles con esta vista.
                allowed = {
                    "busStop",
                    "trainStop",
                    "access",
                    "ptLine",
                    "route",
                    "routeDistribution",
                    "vType",
                    "vTypeDistribution",
                    "param",
                    "tlLogic",
                    "phase",
                }
                with source.open("rb") as stream:
                    for _, element in ET.iterparse(stream, events=("start",)):
                        if element.tag not in allowed | {
                            "additional",
                            "routes",
                            "vTypeDistribution",
                            "stop",
                            "location",
                            "interval",
                        }:
                            raise ValueError(f"Archivo adicional no admitido: {element.tag}.")
                        if any(key in element.attrib for key in ("file", "output", "href")):
                            raise ValueError("Quita referencias y salidas de archivos adicionales.")
            paths.append(str(source))
        ET.SubElement(inputs, tag, value=",".join(paths))
    for group, allowed in ALLOWED_OPTIONS.items():
        original = root.find(group)
        if original is not None:
            target = ET.SubElement(copied, group)
            for child in original:
                if child.tag in allowed and "value" in child.attrib:
                    ET.SubElement(target, child.tag, value=child.attrib["value"])
    write_xml(destination, copied)
    return digest.hexdigest()


def sha256_file(stream):
    digest = sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.digest()


def parse_output(directory, prefix, stop_id, lane_names):
    trips, stops, departures = [], [], defaultdict(list)
    for _, elem in ET.iterparse(directory / "trips.xml"):
        if elem.tag == "tripinfo" and elem.attrib["id"].startswith(prefix):
            a = elem.attrib
            trips.append(
                {
                    "id": a["id"],
                    "travel_s": float(a["duration"]),
                    "distance_m": float(a["routeLength"]),
                    "delay_s": float(a["timeLoss"]),
                    "waiting_s": float(a["waitingTime"]),
                    "departure_delay_s": float(a["departDelay"]),
                    "depart_s": float(a["depart"]),
                    "arrival_s": float(a["arrival"]),
                }
            )
        elem.clear()
    if not trips:
        raise ValueError("La corrida no contiene viajes completos con el prefijo seleccionado.")
    path = directory / "stops.xml"
    if path.is_file():
        for _, elem in ET.iterparse(path):
            if elem.tag in {"stopinfo", "stop"} and elem.get("id", "").startswith(prefix):
                a = elem.attrib
                if "started" not in a or "ended" not in a:
                    elem.clear()
                    continue
                station = a.get("busStop", a.get("trainStop", a.get("lane", "?")))
                entry = {
                    "id": a["id"],
                    "station": station,
                    "dwell_s": float(a["ended"]) - float(a["started"]),
                    "departure_s": float(a["ended"]),
                    "boarded": int(a.get("loadedPersons", "0")),
                    "alighted": int(a.get("unloadedPersons", "0")),
                }
                stops.append(entry)
                departures[station].append(entry["departure_s"])
            elem.clear()
    if stop_id and stop_id not in departures:
        raise ValueError("No se encontraron detenciones completas en la parada de regularidad.")
    times = sorted(departures.get(stop_id, []))
    headways = [(b - a) / 60 for a, b in zip(times, times[1:], strict=False) if b > a]
    ties = sum(b == a for a, b in zip(times, times[1:], strict=False))
    queues = {lane: [] for lane in lane_names}
    if queues:
        for _, elem in ET.iterparse(directory / "queues.xml"):
            if elem.tag == "lane" and elem.get("id") in queues:
                queue = elem.get("queueing_length") or elem.get("queueing_length_experimental")
                if queue is not None:
                    queues[elem.attrib["id"]].append(float(queue))
            elem.clear()
    return {
        "trips": trips,
        "stops": stops,
        "headways_min": headways,
        "quality": service_quality(0, tuple(headways), False, False),
        "same_time_departures": ties,
        "queues": {lane: max(values) if values else None for lane, values in queues.items()},
        "travel_mean_s": mean(t["travel_s"] for t in trips),
        "delay_mean_s": mean(t["delay_s"] for t in trips),
        "speed_kmh": 3.6 * sum(t["distance_m"] for t in trips) / sum(t["travel_s"] for t in trips),
        "dwell_mean_s": mean(t["dwell_s"] for t in stops) if stops else None,
    }


def simulate_corridor(configuration, executable, prefix, stop_id, lanes, seed, cancel):
    if not prefix.strip():
        raise ValueError("Indica el prefijo que identifica los vehículos del servicio.")
    if not 0 <= seed <= 2_147_483_647:
        raise ValueError("Semilla fuera de rango.")
    if cancel.is_set():
        raise SimulationCancelled()
    path = Path(configuration).expanduser().resolve(strict=True)
    with TemporaryDirectory(prefix="hcnet-transit-") as temp:
        directory = Path(temp)
        config = directory / "corridor.sumocfg"
        source_hash = _copy_configuration(path, config)
        if cancel.is_set():
            raise SimulationCancelled()
        version, *_ = _command([str(executable), "--version"], directory, cancel).splitlines()
        _command(
            [
                str(executable),
                "-c",
                str(config),
                "--seed",
                str(seed),
                "--tripinfo-output",
                "trips.xml",
                "--stop-output",
                "stops.xml",
                *(["--queue-output", "queues.xml"] if lanes else []),
                "--no-step-log",
                "true",
                "--duration-log.disable",
                "true",
            ],
            directory,
            cancel,
        )
        result = parse_output(directory, prefix, stop_id, lanes)
        return result | {
            "configuration": str(path),
            "source_hash": source_hash,
            "seed": seed,
            "version": version,
            "prefix": prefix,
            "reference_stop": stop_id,
        }
