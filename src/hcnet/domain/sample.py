"""Caso demostrativo reproducible incluido con HCNet Transport."""

from __future__ import annotations

from hcnet.domain.models import IntersectionProject, LaneGroupInput


def demonstration_project() -> IntersectionProject:
    """Construye un caso hipotético de cuatro accesos y ocho grupos."""

    common = {
        "peak_hour_factor": 0.92,
        "base_saturation_flow_pc_h_ln": 1900.0,
        "heavy_vehicles_percent": 4.0,
        "heavy_vehicle_equivalency": 2.0,
        "lane_width_m": 3.5,
        "incremental_delay_factor": 0.5,
        "upstream_filtering_factor": 1.0,
    }
    groups = [
        LaneGroupInput(
            approach="Norte",
            movement="Izquierda",
            volume_veh_h=145,
            lanes=1,
            effective_green_s=18,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            approach="Norte",
            movement="Directo + derecha",
            volume_veh_h=640,
            lanes=2,
            effective_green_s=43,
            lane_utilization_factor=0.95,
            turn_factor=0.98,
            bus_blockages_h=8,
            **common,
        ),
        LaneGroupInput(
            approach="Sur",
            movement="Izquierda",
            volume_veh_h=125,
            lanes=1,
            effective_green_s=18,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            approach="Sur",
            movement="Directo + derecha",
            volume_veh_h=590,
            lanes=2,
            effective_green_s=43,
            lane_utilization_factor=0.95,
            turn_factor=0.98,
            **common,
        ),
        LaneGroupInput(
            approach="Oriente",
            movement="Izquierda",
            volume_veh_h=110,
            lanes=1,
            effective_green_s=15,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            approach="Oriente",
            movement="Directo + derecha",
            volume_veh_h=485,
            lanes=2,
            effective_green_s=37,
            lane_utilization_factor=0.95,
            turn_factor=0.98,
            parking_maneuvers_h=6,
            **common,
        ),
        LaneGroupInput(
            approach="Poniente",
            movement="Izquierda",
            volume_veh_h=105,
            lanes=1,
            effective_green_s=15,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            approach="Poniente",
            movement="Directo + derecha",
            volume_veh_h=460,
            lanes=2,
            effective_green_s=37,
            lane_utilization_factor=0.95,
            turn_factor=0.98,
            **common,
        ),
    ]
    return IntersectionProject(
        name="Av. Universidad × Eje 10 Sur (caso demostrativo)",
        location="Ciudad de México",
        analyst="",
        study_date="2026-09-11",
        cycle_length_s=100.0,
        analysis_period_h=0.25,
        lane_groups=groups,
        notes=(
            "Caso hipotético con fines docentes. Los datos no representan un aforo real "
            "ni deben utilizarse para decisiones de proyecto."
        ),
    )
