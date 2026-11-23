"""Caso demostrativo reproducible incluido con HCNet Transport."""

from __future__ import annotations

from hcnet.domain.models import IntersectionProject, LaneGroupInput, SignalHeadInput
from hcnet.domain.roundabout import RoundaboutInput
from hcnet.domain.transit import TransitLineInput


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
            identifier="demo-n-li",
            origin_branch="A",
            destination_branches=("B",),
            lane_indices=(1,),
            signal_phase=1,
            approach="Norte",
            movement="Izquierda",
            volume_veh_h=145,
            lanes=1,
            effective_green_s=18,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            identifier="demo-n-dr",
            origin_branch="A",
            destination_branches=("C", "D"),
            lane_indices=(2, 3),
            signal_phase=2,
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
            identifier="demo-s-li",
            origin_branch="C",
            destination_branches=("D",),
            lane_indices=(1,),
            signal_phase=1,
            approach="Sur",
            movement="Izquierda",
            volume_veh_h=125,
            lanes=1,
            effective_green_s=18,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            identifier="demo-s-dr",
            origin_branch="C",
            destination_branches=("A", "B"),
            lane_indices=(2, 3),
            signal_phase=2,
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
            identifier="demo-e-li",
            origin_branch="B",
            destination_branches=("C",),
            lane_indices=(1,),
            signal_phase=3,
            approach="Oriente",
            movement="Izquierda",
            volume_veh_h=110,
            lanes=1,
            effective_green_s=15,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            identifier="demo-e-dr",
            origin_branch="B",
            destination_branches=("D", "A"),
            lane_indices=(2, 3),
            signal_phase=4,
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
            identifier="demo-w-li",
            origin_branch="D",
            destination_branches=("A",),
            lane_indices=(1,),
            signal_phase=3,
            approach="Poniente",
            movement="Izquierda",
            volume_veh_h=105,
            lanes=1,
            effective_green_s=15,
            turn_factor=0.95,
            **common,
        ),
        LaneGroupInput(
            identifier="demo-w-dr",
            origin_branch="D",
            destination_branches=("B", "C"),
            lane_indices=(2, 3),
            signal_phase=4,
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
    heads = [
        SignalHeadInput(
            identifier=f"demo-s{index + 1}",
            name=f"S{index + 1} · {group.label}",
            branch_code=group.origin_branch,
            signal_type=(
                "Flecha direccional"
                if "Izquierda" in group.movement
                else "Vehicular circular"
            ),
            signal_phase=group.signal_phase,
            controlled_group_ids=(group.identifier,),
        )
        for index, group in enumerate(groups)
    ]
    roundabout = RoundaboutInput(
        name="Rotonda de cuatro accesos (caso demostrativo)", arm_count=4,
        diameter_m=38, circulating_width_m=6, apron_width_m=2, design_speed_kmh=25,
        peak_hour_factor=0.92,
    )
    for i, name in enumerate(("Norte", "Oriente", "Sur", "Poniente")):
        arm = roundabout.arms[i]
        arm.name = name
        arm.azimuth_deg = 90 * i
        arm.entry_width_m = 4
        arm.exit_width_m = 4.5
        arm.entry_radius_m = 19
        arm.exit_radius_m = 32
        arm.storage_m = 45
        arm.heavy_percent = 4
        roundabout.flows[i][:4] = [0 if i == j else 80 + 20*j for j in range(4)]
    return IntersectionProject(
        name="Av. Universidad × Eje 10 Sur (caso demostrativo)",
        location="Ciudad de México",
        analyst="",
        study_date="2026-09-11",
        cycle_length_s=100.0,
        analysis_period_h=0.25,
        lane_groups=groups,
        signal_heads=heads,
        roundabout=roundabout,
        public_transport=TransitLineInput(
            name="Corredor Universidad (caso demostrativo)",
            route_length_km=12.0,
            stop_count_per_direction=25,
            operating_speed_kmh=28.0,
            terminal_layover_min=8.0,
            scheduled_headway_min=8.0,
            vehicle_capacity_pax=80.0,
            target_load_factor=0.85,
            peak_demand_pax_h_direction=500.0,
        ),
        notes=(
            "Caso hipotético con fines docentes. Los datos no representan un aforo real "
            "ni deben utilizarse para decisiones de proyecto."
        ),
    )
