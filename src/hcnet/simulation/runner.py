"""Ejecuta netconvert y SUMO sin ventanas y recupera un experimento completo."""

import os
import re
import signal
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from secrets import randbelow
from subprocess import Popen, TimeoutExpired
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from xml.etree import ElementTree as ET

from hcnet.domain.models import IntersectionProject
from hcnet.domain.scenarios import baseline_key
from hcnet.simulation.network import install_program, write_demand, write_network, write_xml
from hcnet.simulation.options import FleetType, SimulationOptions, validate_fleet
from hcnet.simulation.results import parse_run, stats


class SimulationCancelled(Exception):
    """El usuario detuvo el experimento."""


def _command(args: list[str], directory: Path, cancel: Event) -> str:
    deadline = monotonic() + 600
    log = directory / "engine.log"
    with (
        log.open("w+b") as stream,
        Popen(
            args,
            cwd=directory,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        ) as process,
    ):
        while process.poll() is None:
            timed_out = monotonic() >= deadline
            if cancel.wait(0.1) or timed_out:
                # Los lanzadores de los paquetes Python pueden crear otro proceso.
                _signal_group(process.pid, signal.SIGTERM)
                try:
                    process.wait(2)
                except TimeoutExpired:
                    pass
                _signal_group(process.pid, signal.SIGKILL)
                process.wait()
                if cancel.is_set():
                    raise SimulationCancelled()
                raise ValueError(f"{Path(args[0]).name} excedió el tiempo máximo de ejecución.")
        code = process.returncode
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 4000))
        output = stream.read().decode(errors="replace")
    if code:
        raise ValueError(f"{Path(args[0]).name}: {output.strip()}")
    return output


def _signal_group(pid: int, action: int) -> None:
    try:
        os.killpg(pid, action)
    except ProcessLookupError:
        pass


def simulate(
    project: IntersectionProject,
    options: SimulationOptions,
    fleet: tuple[FleetType, ...],
    binaries: tuple[Path, Path],
    cancel: Event,
    progress=lambda current, total: None,
) -> dict:
    options.validate()
    validate_fleet(fleet, simulated=True)

    def check() -> None:
        if cancel.is_set():
            raise SimulationCancelled()

    check()
    sumo, netconvert = map(str, binaries)
    first_seed = options.seed if options.seed is not None else randbelow(2_147_483_630)
    seeds = list(range(first_seed, first_seed + options.runs))
    runs = []
    with TemporaryDirectory(prefix="hcnet-sumo-") as folder:
        directory = Path(folder)
        output = _command([sumo, "--version"], directory, cancel)
        version = output.strip().split("\n", 1)[0]
        version_number = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
        if not version_number or tuple(map(int, version_number.groups())) < (1, 14, 0):
            raise ValueError("Se requiere SUMO 1.14 o posterior para las unidades del combustible.")
        network = write_network(project, directory)
        geometry = sha256(
            (directory / "nodes.xml").read_bytes() + (directory / "edges.xml").read_bytes()
        ).hexdigest()
        _command(
            [
                netconvert,
                "--node-files",
                "nodes.xml",
                "--edge-files",
                "edges.xml",
                "--connection-files",
                "turns.xml",
                "--no-turnarounds",
                "true",
                "--output-file",
                "intersection.net.xml",
                "--xml-validation",
                "never",
            ],
            directory,
            cancel,
        )
        install_program(directory / "intersection.net.xml", network)
        additional = ET.Element("additional")
        ET.SubElement(
            additional, "timedEvent", type="SaveTLSStates", source="J", dest="signals.xml.gz"
        )
        write_xml(directory / "signals.add.xml", additional)
        for index, seed in enumerate(seeds, 1):
            check()
            progress(index, options.runs)
            planned = write_demand(directory / "demand.rou.xml", network, options, fleet, seed)
            output = _command(
                [
                    sumo,
                    "--net-file",
                    "intersection.net.xml",
                    "--route-files",
                    "demand.rou.xml",
                    "--xml-validation",
                    "never",
                    "--additional-files",
                    "signals.add.xml",
                    "--step-length",
                    "1",
                    "--seed",
                    str(seed),
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
            row = parse_run(directory, network, options, planned, seed, check)
            row["warnings"] = [line for line in output.splitlines() if "Warning:" in line][-12:]
            runs.append(row)
    check()
    names = dict.fromkeys(name for row in runs for name in row["metrics"])
    return {
        "scenario_key": baseline_key(project),
        "sumo": version,
        "geometry": geometry,
        "options": asdict(options),
        "demand": [{**asdict(route), "lanes": list(route.lanes)} for route in network.routes],
        "fleet": [asdict(v) for v in fleet],
        "lanes": list(map(list, network.lanes.values())),
        "program": {
            **asdict(network.program),
            "phases": [asdict(p) for p in network.program.phases],
            "warnings": list(network.program.warnings),
        },
        "runs": runs,
        "metrics": {
            name: stats([r["metrics"][name] for r in runs if name in r["metrics"]])
            for name in names
        },
        "emissions": {
            name: stats([r["emissions"][name] for r in runs]) for name in runs[0]["emissions"]
        },
    }
