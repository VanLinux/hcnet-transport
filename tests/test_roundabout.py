from math import exp

import pytest

from hcnet.domain.roundabout import RoundaboutInput, calculate_roundabout


def test_conflicts_follow_circulation_and_exclude_the_destination() -> None:
    data = RoundaboutInput(
        arm_count=4, circulation="Horario", diameter_m=40,
        circulating_width_m=6, design_speed_kmh=25,
    )
    data.flows[3][1] = 160  # D → A (pasa) → B (sale)
    data.flows[3][3] = 40   # vuelta en U: cruza A, B y C
    data.arms[3].heavy_percent = 25
    result = calculate_roundabout(data)
    assert [a.conflicting for a in result.arms] == [200, 40, 40, 0]
    assert result.arms[0].capacity == pytest.approx(1130 * exp(-0.25))
    assert result.arms[3].queue_95 > 0
    assert result.arms[0].los == "—"
    assert result.total_entry == 200

    data.circulation = "Antihorario"
    assert [a.conflicting for a in calculate_roundabout(data).arms] == [40, 40, 200, 0]


def test_roundabout_geometry_from_chord_sagitta_and_azimuths() -> None:
    data = RoundaboutInput(
        circulation="Horario", diameter_m=40, circulating_width_m=6,
        apron_width_m=2, design_speed_kmh=25,
    )
    data.arms[0].entry_chord_m = 16
    data.arms[0].entry_sagitta_m = 2
    result = calculate_roundabout(data)
    assert result.island_radius == 14
    assert result.hard_island_radius == 12
    assert result.centerline_radius == 17
    assert result.arms[0].entry_radius == 17
    assert result.arms[0].next_angle == 45
    assert result.arms[2].next_angle == 270

    data.arms[0].entry_radius_m = 30
    with pytest.raises(ValueError, match="radio directo o cuerda"):
        calculate_roundabout(data)
