from __future__ import annotations

from hcnet.domain.models import IntersectionProject, LaneGroupInput
from hcnet.domain.validation import validate_project


def test_empty_project_has_actionable_error() -> None:
    project = IntersectionProject(lane_groups=[])
    issues = validate_project(project)

    assert any(issue.field == "lane_groups" and issue.severity == "error" for issue in issues)


def test_unusual_cycle_and_saturation_flow_are_warnings() -> None:
    project = IntersectionProject(
        cycle_length_s=260,
        lane_groups=[LaneGroupInput(base_saturation_flow_pc_h_ln=2300, effective_green_s=40)],
    )
    issues = validate_project(project)

    warning_fields = {issue.field for issue in issues if issue.severity == "warning"}
    assert "cycle_length_s" in warning_fields
    assert "base_saturation_flow_pc_h_ln" in warning_fields
    assert not [issue for issue in issues if issue.severity == "error"]


def test_invalid_phf_and_width_are_errors() -> None:
    project = IntersectionProject(
        lane_groups=[LaneGroupInput(peak_hour_factor=1.2, lane_width_m=2.0)]
    )
    errors = [issue.field for issue in validate_project(project) if issue.severity == "error"]

    assert "peak_hour_factor" in errors
    assert "lane_width_m" in errors


def test_three_leg_geometry_accepts_only_active_destinations() -> None:
    valid = IntersectionProject(
        branch_count=3,
        lane_groups=[
            LaneGroupInput(
                origin_branch="A",
                destination_branches=("B",),
                lane_indices=(1,),
            )
        ],
    )
    invalid = IntersectionProject(
        branch_count=3,
        lane_groups=[
            LaneGroupInput(
                origin_branch="A",
                destination_branches=("D",),
                lane_indices=(1,),
            )
        ],
    )

    assert not [issue for issue in validate_project(valid) if issue.severity == "error"]
    assert any(
        issue.field == "destination_branches" and issue.severity == "error"
        for issue in validate_project(invalid)
    )


def test_overlapping_lane_groups_generate_capacity_warning() -> None:
    first = LaneGroupInput(identifier="first", lane_indices=(1,))
    second = LaneGroupInput(
        identifier="second",
        destination_branches=("B",),
        lane_indices=(1,),
    )
    project = IntersectionProject(lane_groups=[first, second])

    assert any(
        issue.field == "lane_groups" and "duplicar capacidad" in issue.message
        for issue in validate_project(project)
    )
