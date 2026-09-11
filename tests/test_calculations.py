from __future__ import annotations

from dataclasses import replace

import pytest

from hcnet.domain.calculations import (
    CalculationError,
    adjustment_factors,
    calculate_intersection,
    calculate_lane_group,
    level_of_service,
)
from hcnet.domain.models import IntersectionProject, LaneGroupInput
from hcnet.domain.sample import demonstration_project


def basic_project(**overrides) -> IntersectionProject:
    group = LaneGroupInput(
        identifier="test-group",
        approach="Norte",
        movement="Directo",
        volume_veh_h=600,
        lanes=1,
        effective_green_s=48,
        peak_hour_factor=1.0,
        base_saturation_flow_pc_h_ln=1900,
        heavy_vehicles_percent=0,
        lane_width_m=3.6,
        grade_percent=0,
        parking_maneuvers_h=0,
        bus_blockages_h=0,
        lane_utilization_factor=1,
        area_type_factor=1,
        turn_factor=1,
        progression_factor=1,
        incremental_delay_factor=0.5,
        upstream_filtering_factor=1,
    )
    group = replace(group, **overrides)
    return IntersectionProject(
        name="Caso de prueba",
        cycle_length_s=120,
        analysis_period_h=0.25,
        lane_groups=[group],
    )


def replace_group(group: LaneGroupInput, **overrides) -> LaneGroupInput:
    return replace(group, **overrides)


def test_default_adjustment_factors_are_traceable() -> None:
    group = basic_project().lane_groups[0]
    factors = adjustment_factors(group)

    assert factors.lane_width == pytest.approx(1.0)
    assert factors.heavy_vehicles == pytest.approx(1.0)
    assert factors.grade == pytest.approx(1.0)
    assert factors.parking == pytest.approx(1.0)
    assert factors.bus_blockage == pytest.approx(1.0)
    assert factors.product == pytest.approx(1.0)


def test_heavy_vehicle_factor_uses_passenger_car_equivalency() -> None:
    group = basic_project(
        heavy_vehicles_percent=10,
        heavy_vehicle_equivalency=2,
    ).lane_groups[0]
    assert adjustment_factors(group).heavy_vehicles == pytest.approx(1 / 1.1)


def test_lane_group_capacity_degree_delay_and_los() -> None:
    project = basic_project(parking_maneuvers_h=0)
    result = calculate_lane_group(project, project.lane_groups[0])

    expected_saturation = 1900
    expected_capacity = expected_saturation * (48 / 120)
    expected_x = 600 / expected_capacity
    expected_d1 = 0.5 * 120 * (1 - 0.4) ** 2 / (1 - expected_x * 0.4)
    expected_d2 = (
        900
        * 0.25
        * (
            (expected_x - 1)
            + ((expected_x - 1) ** 2 + 8 * 0.5 * 1 * expected_x / (expected_capacity * 0.25)) ** 0.5
        )
    )

    assert result.saturation_flow_veh_h == pytest.approx(expected_saturation)
    assert result.capacity_veh_h == pytest.approx(expected_capacity)
    assert result.degree_of_saturation == pytest.approx(expected_x)
    assert result.uniform_delay_s_veh == pytest.approx(expected_d1)
    assert result.incremental_delay_s_veh == pytest.approx(expected_d2)
    assert result.control_delay_s_veh == pytest.approx(expected_d1 + expected_d2)
    assert result.level_of_service == "D"


@pytest.mark.parametrize(
    ("delay", "expected"),
    [(0, "A"), (10, "A"), (10.01, "B"), (20, "B"), (35, "C"), (55, "D"), (80, "E"), (80.01, "F")],
)
def test_los_delay_boundaries(delay: float, expected: str) -> None:
    assert level_of_service(delay) == expected


def test_oversaturated_lane_group_is_los_f() -> None:
    project = basic_project(volume_veh_h=1400)
    result = calculate_lane_group(project, project.lane_groups[0])

    assert result.degree_of_saturation > 1
    assert result.level_of_service == "F"
    assert result.residual_demand_veh > 0
    assert any("superior a la capacidad" in warning for warning in result.warnings)


def test_intersection_delay_is_weighted_by_adjusted_demand() -> None:
    project = basic_project()
    first = project.lane_groups[0]
    second = replace_group(
        first,
        identifier="second",
        approach="Sur",
        volume_veh_h=300,
        effective_green_s=60,
    )
    project.lane_groups.append(second)
    result = calculate_intersection(project)
    expected = (
        result.lane_groups[0].control_delay_s_veh * 600
        + result.lane_groups[1].control_delay_s_veh * 300
    ) / 900

    assert result.weighted_control_delay_s_veh == pytest.approx(expected)
    assert result.critical_lane_group == "Norte · Directo"


def test_invalid_green_is_rejected_before_calculation() -> None:
    project = basic_project(effective_green_s=120)
    with pytest.raises(CalculationError, match="verde efectivo"):
        calculate_intersection(project)


def test_non_finite_input_is_rejected() -> None:
    project = basic_project(volume_veh_h=float("nan"))
    with pytest.raises(CalculationError, match="número finito"):
        calculate_intersection(project)


def test_demonstration_project_produces_finite_results() -> None:
    result = calculate_intersection(demonstration_project())

    assert len(result.lane_groups) == 8
    assert result.total_entering_volume_veh_h == pytest.approx(2660)
    assert 0 < result.weighted_control_delay_s_veh < 200
    assert result.level_of_service in set("ABCDEF")
