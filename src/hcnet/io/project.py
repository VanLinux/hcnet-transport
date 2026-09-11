"""Lectura, escritura y exportación de archivos de HCNet Transport."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from hcnet.domain.models import IntersectionProject, IntersectionResult
from hcnet.domain.reporting import latex_report


def load_project(path: str | Path) -> IntersectionProject:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"El archivo no contiene JSON válido (línea {exc.lineno}, columna {exc.colno})."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("La raíz del archivo debe ser un objeto JSON.")
    return IntersectionProject.from_dict(payload)


def save_project(project: IntersectionProject, path: str | Path) -> Path:
    """Guarda de forma atómica para evitar proyectos parcialmente escritos."""

    destination = Path(path)
    serialized = json.dumps(project.to_dict(), ensure_ascii=False, indent=2) + "\n"
    return _atomic_write_text(destination, serialized)


def export_results_csv(
    project: IntersectionProject,
    result: IntersectionResult,
    path: str | Path,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    groups_by_id = {group.identifier: group for group in project.lane_groups}

    columns = [
        "proyecto",
        "ubicacion",
        "acceso",
        "movimiento",
        "volumen_veh_h",
        "flujo_ajustado_veh_h",
        "flujo_saturacion_veh_h",
        "capacidad_veh_h",
        "grado_saturacion_X",
        "demora_uniforme_d1_s_veh",
        "demora_incremental_d2_s_veh",
        "demora_cola_inicial_d3_s_veh",
        "demora_control_s_veh",
        "nivel_servicio",
        "llegadas_en_rojo_veh_ciclo",
        "demanda_residual_veh",
        "fw",
        "fHV",
        "fg",
        "fp",
        "fbb",
        "fLU",
        "fa",
        "fturn",
        "producto_factores",
    ]

    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in result.lane_groups:
            source = groups_by_id[row.identifier]
            writer.writerow(
                {
                    "proyecto": project.name,
                    "ubicacion": project.location,
                    "acceso": source.approach,
                    "movimiento": source.movement,
                    "volumen_veh_h": _number(source.volume_veh_h),
                    "flujo_ajustado_veh_h": _number(row.demand_flow_rate_veh_h),
                    "flujo_saturacion_veh_h": _number(row.saturation_flow_veh_h),
                    "capacidad_veh_h": _number(row.capacity_veh_h),
                    "grado_saturacion_X": _number(row.degree_of_saturation, 4),
                    "demora_uniforme_d1_s_veh": _number(row.uniform_delay_s_veh),
                    "demora_incremental_d2_s_veh": _number(row.incremental_delay_s_veh),
                    "demora_cola_inicial_d3_s_veh": _number(row.initial_queue_delay_s_veh),
                    "demora_control_s_veh": _number(row.control_delay_s_veh),
                    "nivel_servicio": row.level_of_service,
                    "llegadas_en_rojo_veh_ciclo": _number(row.red_arrivals_veh_cycle),
                    "demanda_residual_veh": _number(row.residual_demand_veh),
                    "fw": _number(row.factors.lane_width, 4),
                    "fHV": _number(row.factors.heavy_vehicles, 4),
                    "fg": _number(row.factors.grade, 4),
                    "fp": _number(row.factors.parking, 4),
                    "fbb": _number(row.factors.bus_blockage, 4),
                    "fLU": _number(row.factors.lane_utilization, 4),
                    "fa": _number(row.factors.area_type, 4),
                    "fturn": _number(row.factors.turn, 4),
                    "producto_factores": _number(row.factors.product, 4),
                }
            )

    return destination


def export_report_tex(
    project: IntersectionProject,
    result: IntersectionResult,
    path: str | Path,
) -> Path:
    """Exporta un reporte técnico completo como código fuente LaTeX UTF-8."""

    destination = Path(path)
    return _atomic_write_text(destination, latex_report(project, result))


def _atomic_write_text(destination: Path, content: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return destination


def _number(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"
