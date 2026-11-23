from __future__ import annotations

from dataclasses import replace
from math import exp, sqrt

import pytest

from hcnet.domain.transit import (
    TransitCalculationError,
    TransitLineInput,
    calculate_transit_line,
    congestion_time,
)


def test_operational_plan_calculates_speed_cycle_fleet_and_capacity() -> None:
    data = TransitLineInput()
    result = calculate_transit_line(data)

    assert result.running_time_one_way_min == pytest.approx(60 * 12 / 28)
    assert result.boarding_service_time_s == pytest.approx(8 * 2.5 / 2)
    assert result.alighting_service_time_s == pytest.approx(7 * 1.8 / 2)
    assert result.dwell_time_s == pytest.approx(14)
    assert result.commercial_time_one_way_min == pytest.approx(35.68095238)
    assert result.commercial_speed_kmh == pytest.approx(20.17883358)
    assert result.cycle_time_min == pytest.approx(87.36190476)
    assert result.service_frequency_bus_h == pytest.approx(7.5)
    assert result.line_capacity_pax_h_direction == pytest.approx(510)
    assert result.minimum_fleet_veh == 11
    assert result.reserve_fleet_veh == 2
    assert result.total_fleet_veh == 13


def test_stop_spacing_balances_access_and_in_vehicle_stop_penalty() -> None:
    data = TransitLineInput()
    result = calculate_transit_line(data)
    expected = sqrt(4 * 1.2 * 5000 * (14 + 12))

    assert result.actual_stop_spacing_m == pytest.approx(500)
    assert result.average_access_time_min == pytest.approx(500 / (4 * 1.2) / 60)
    assert result.optimal_stop_spacing_m == pytest.approx(expected)
    assert result.recommended_stop_count == 16


def test_sequential_exchange_adds_boarding_and_alighting_times() -> None:
    data = replace(TransitLineInput(), exchange_mode="Secuencial")
    result = calculate_transit_line(data)

    assert result.dwell_time_s == pytest.approx(4 + 10 + 6.3)
    simultaneous_speed = calculate_transit_line(TransitLineInput()).commercial_speed_kmh
    assert result.commercial_speed_kmh < simultaneous_speed


def test_demand_deficit_reports_required_service_and_warning() -> None:
    data = replace(TransitLineInput(), peak_demand_pax_h_direction=1000)
    result = calculate_transit_line(data)

    assert result.capacity_margin_pax_h_direction == pytest.approx(-490)
    assert result.required_frequency_bus_h == pytest.approx(1000 / 68)
    assert result.required_headway_min == pytest.approx(60 / (1000 / 68))
    assert any("no cubre" in warning for warning in result.warnings)


def test_congestion_models_match_configured_equations() -> None:
    data = TransitLineInput()
    t0 = 20.0
    degree = 0.75

    assert congestion_time("Lineal", t0, degree, data) == pytest.approx(
        t0 * (1 + data.linear_alpha * degree)
    )
    assert congestion_time("BPR", t0, degree, data) == pytest.approx(
        t0 * (1 + data.bpr_alpha * degree**data.bpr_beta)
    )
    assert congestion_time("Davidson", t0, degree, data) == pytest.approx(
        t0 * (1 + data.davidson_j * degree / (1 - degree))
    )
    assert congestion_time("Exponencial", t0, degree, data) == pytest.approx(
        t0 * exp(data.exponential_alpha * degree)
    )
    assert congestion_time("Davidson", t0, 1.0, data) is None


def test_oversaturated_road_marks_davidson_as_non_finite() -> None:
    result = calculate_transit_line(replace(TransitLineInput(), road_capacity_veh_h=900))
    davidson = next(item for item in result.congestion if item.model == "Davidson")

    assert result.road_degree_of_saturation > 1
    assert davidson.travel_time_min is None
    assert any("Davidson" in warning for warning in result.warnings)


def test_invalid_line_is_rejected_independently() -> None:
    with pytest.raises(TransitCalculationError, match="al menos dos"):
        calculate_transit_line(replace(TransitLineInput(), stop_count_per_direction=1))
