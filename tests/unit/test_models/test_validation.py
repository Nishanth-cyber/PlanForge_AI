"""Unit tests for Validation data contracts."""

from app.models.validation import ValidationIssue, ValidationResult, ValidationReport


def test_validation_issue_creation():
    """Test ValidationIssue fields including target_id linkage."""
    issue = ValidationIssue(
        severity="error",
        category="boundary",
        message="Room extends outside buildable plot boundary",
        details={"spill_sqm": 2.4},
        target_id="room_living_01",
    )
    assert issue.id is not None
    assert issue.severity == "error"
    assert issue.category == "boundary"
    assert issue.target_id == "room_living_01"


def test_warning_does_not_mark_category_passed():
    """Verify the critical fix: warnings do NOT mark category as passed."""
    val = ValidationResult(floor_number=1)
    issue = ValidationIssue(
        severity="warning",
        category="aspect_ratio",
        message="Room aspect ratio is 2.2, slightly above recommended 2.0",
    )
    val.add_issue(issue)

    assert val.is_valid is True  # Warning does not invalidate floor plan
    assert "aspect_ratio" in val.checks_warned
    assert "aspect_ratio" not in val.checks_passed  # CRUCIAL: Not in passed!
    assert "aspect_ratio" not in val.checks_failed
    assert val.has_warnings is True
    assert val.has_errors is False
    assert val.warning_count == 1
    assert val.error_count == 0


def test_error_invalidates_and_marks_failed():
    """Verify that error severity invalidates and records failed check."""
    val = ValidationResult(floor_number=1)
    val.record_passed_check("overlap")  # Pretend it previously passed
    assert "overlap" in val.checks_passed

    error = ValidationIssue(
        severity="error",
        category="overlap",
        message="Bedroom overlaps with Bathroom",
    )
    val.add_issue(error)

    assert val.is_valid is False
    assert "overlap" in val.checks_failed
    assert "overlap" not in val.checks_passed  # Removed from passed
    assert val.has_errors is True
    assert val.error_count == 1


def test_record_passed_check():
    """Verify record_passed_check records cleanly and does not overwrite failed checks."""
    val = ValidationResult(floor_number=1)
    val.record_passed_check("connectivity")
    assert "connectivity" in val.checks_passed

    # Should not re-add duplicate
    val.record_passed_check("connectivity")
    assert val.checks_passed.count("connectivity") == 1


def test_validation_report_aggregation_and_iteration():
    """Test ValidationReport with overall score, errors, warnings, and iteration index."""
    v1 = ValidationResult(floor_number=1, score=90.0, is_valid=True)
    v1.add_issue(ValidationIssue(severity="warning", category="dimension", message="Low clearance"))

    v2 = ValidationResult(floor_number=2, score=60.0, is_valid=False)
    v2.add_issue(ValidationIssue(severity="error", category="door", message="Missing door"))

    report = ValidationReport(
        results=[v1, v2],
        iteration=2,
    )

    assert report.iteration == 2
    assert report.overall_valid is False
    assert report.overall_score == 75.0
    assert report.total_errors == 1
    assert report.total_warnings == 1
    assert report.get_result(1) == v1
    assert report.get_result(2) == v2
    assert report.get_result(3) is None
