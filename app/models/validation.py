"""Validation models for deterministic floor plan verification.

The Validator represents VERIFY:
- Strict separation between error (failure), warning (advisory), and passed checks
- Warnings do NOT mark validation categories as passed
- Detailed issue records linking to affected room/door/wall IDs
- Multi-floor composite validation reports with refinement iteration tracking
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class ValidationIssue:
    """A single validation issue reported by a deterministic check."""
    id: str = field(default_factory=generate_id)
    severity: str = "error"  # "error", "warning", "info"
    category: str = ""  # e.g. "boundary", "overlap", "dimension", "connectivity", "relationship", "staircase", "door", "window"
    message: str = ""
    details: Optional[dict] = None
    location: Optional[dict] = None
    target_id: Optional[str] = None  # ID of affected room, wall, door, or window
    floor_number: int = 1
    room_id: Optional[str] = None
    check: str = ""

    def __post_init__(self) -> None:
        if not self.check and self.category:
            self.check = self.category
        elif not self.category and self.check:
            self.category = self.check
        if not self.room_id and self.target_id:
            self.room_id = self.target_id


@dataclass
class ValidationResult:
    """Result of deterministic validation for a single floor."""
    id: str = field(default_factory=generate_id)
    floor_number: int = 1
    is_valid: bool = True
    score: float = 100.0
    issues: list[ValidationIssue] = field(default_factory=list)
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    checks_warned: list[str] = field(default_factory=list)

    def add_issue(self, issue: ValidationIssue) -> None:
        """Record an issue and update check categories appropriately.

        Errors invalidate the floor plan and record the category as failed.
        Warnings record advisory issues but do NOT mark the category as passed.
        """
        self.issues.append(issue)
        if issue.severity == "error":
            if issue.category and issue.category not in self.checks_failed:
                self.checks_failed.append(issue.category)
            if issue.category in self.checks_passed:
                self.checks_passed.remove(issue.category)
            self.is_valid = False
        elif issue.severity == "warning":
            if issue.category and issue.category not in self.checks_warned:
                self.checks_warned.append(issue.category)
            # Crucial fix: warnings do NOT mark category as passed!

    def record_passed_check(self, category: str) -> None:
        """Explicitly record that a category check passed without errors."""
        if category and category not in self.checks_failed and category not in self.checks_passed:
            self.checks_passed.append(category)

    @property
    def has_errors(self) -> bool:
        """Check if any error-level issues exist."""
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if any warning-level issues exist."""
        return any(i.severity == "warning" for i in self.issues)

    @property
    def error_count(self) -> int:
        """Number of error-level issues."""
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        """Number of warning-level issues."""
        return sum(1 for i in self.issues if i.severity == "warning")


@dataclass
class ValidationReport:
    """Complete validation report across all floors."""
    id: str = field(default_factory=generate_id)
    results: list[ValidationResult] = field(default_factory=list)
    iteration: int = 0  # Refinement iteration counter

    @property
    def overall_valid(self) -> bool:
        """True only if every floor result is valid."""
        if not self.results:
            return True
        return all(r.is_valid for r in self.results)

    @property
    def overall_score(self) -> float:
        """Average validation score across all floors."""
        if not self.results:
            return 100.0
        return sum(r.score for r in self.results) / len(self.results)

    @property
    def total_errors(self) -> int:
        """Total number of errors across all floors."""
        return sum(r.error_count for r in self.results)

    @property
    def total_warnings(self) -> int:
        """Total number of warnings across all floors."""
        return sum(r.warning_count for r in self.results)

    def get_result(self, floor_number: int) -> Optional[ValidationResult]:
        """Retrieve validation result for a specific floor."""
        for r in self.results:
            if r.floor_number == floor_number:
                return r
        return None

    def all_issues(self) -> list[ValidationIssue]:
        """Aggregate all issues across all floor results."""
        issues: list[ValidationIssue] = []
        for r in self.results:
            issues.extend(r.issues)
        return issues

    def all_errors(self) -> list[ValidationIssue]:
        """Aggregate all error issues across all floor results."""
        return [i for i in self.all_issues() if i.severity == "error"]

    def all_warnings(self) -> list[ValidationIssue]:
        """Aggregate all warning issues across all floor results."""
        return [i for i in self.all_issues() if i.severity == "warning"]
