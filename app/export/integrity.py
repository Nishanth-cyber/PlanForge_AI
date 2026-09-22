"""Export integrity validation utility checking completeness and structural validity of exports."""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union


@dataclass
class ExportIntegrityReport:
    """Report detailing structural integrity of an exported project bundle."""
    bundle_path: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verified_files: List[str] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """Total count of verified files."""
        return len(self.verified_files)

    def summary(self) -> str:
        status = "PASSED" if self.is_valid else "FAILED"
        return (
            f"Export Integrity [{status}]: {len(self.verified_files)} files verified, "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings."
        )


def verify_export_integrity(
    bundle_dir: Union[str, Path],
    expected_floors: int = 1,
    expected_alternatives: int = 0,
    check_images: bool = True,
    check_trace: bool = False,
) -> ExportIntegrityReport:
    """Verify that an exported project bundle is structurally complete and syntactically valid.

    Note: This is an export-integrity validator, NOT an architectural rule validator.
    """
    p = Path(bundle_dir)
    errors: List[str] = []
    warnings: List[str] = []
    verified: List[str] = []

    if not p.exists() or not p.is_dir():
        return ExportIntegrityReport(
            bundle_path=str(p),
            is_valid=False,
            errors=[f"Bundle directory does not exist: {p}"],
        )

    # 1. Check project.json
    proj_json = p / "project.json"
    if not proj_json.exists():
        errors.append("Missing required 'project.json' at root of bundle.")
    else:
        try:
            with open(proj_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                errors.append("'project.json' does not contain a JSON object.")
            elif "project_metadata" not in data:
                warnings.append("'project.json' is missing 'project_metadata'.")
            verified.append(str(proj_json.name))
        except Exception as e:
            errors.append(f"Failed to parse 'project.json': {e}")

    # 2. Check summary.md
    summary_md = p / "summary.md"
    if not summary_md.exists():
        errors.append("Missing required 'summary.md' at root of bundle.")
    else:
        if summary_md.stat().st_size == 0:
            errors.append("'summary.md' is empty.")
        else:
            verified.append(str(summary_md.name))

    # 3. Check decision_trace.json if required
    if check_trace:
        trace_json = p / "decision_trace.json"
        if not trace_json.exists():
            errors.append("Missing required 'decision_trace.json'.")
        else:
            try:
                with open(trace_json, "r", encoding="utf-8") as f:
                    json.load(f)
                verified.append(str(trace_json.name))
            except Exception as e:
                errors.append(f"Invalid JSON in 'decision_trace.json': {e}")

    # 4. Check alternatives
    if expected_alternatives > 0:
        alt_root = p / "alternatives"
        if not alt_root.exists():
            errors.append("Missing 'alternatives/' directory.")
        else:
            for idx in range(1, expected_alternatives + 1):
                alt_dir = alt_root / f"alternative_{idx}"
                if not alt_dir.exists():
                    errors.append(f"Missing directory for alternative {idx}: {alt_dir.name}")
                    continue

                # Check design.json
                d_json = alt_dir / "design.json"
                if not d_json.exists():
                    errors.append(f"Missing 'design.json' in {alt_dir.name}.")
                else:
                    try:
                        with open(d_json, "r", encoding="utf-8") as f:
                            json.load(f)
                        verified.append(f"{alt_dir.name}/design.json")
                    except Exception as e:
                        errors.append(f"Invalid JSON in {alt_dir.name}/design.json: {e}")

                # Check explanation.md
                e_md = alt_dir / "explanation.md"
                if not e_md.exists():
                    warnings.append(f"Missing 'explanation.md' in {alt_dir.name}.")
                else:
                    verified.append(f"{alt_dir.name}/explanation.md")

                # Check rendered floor images
                if check_images:
                    for fn in range(1, expected_floors + 1):
                        img = alt_dir / f"floor_{fn}.png"
                        if not img.exists():
                            errors.append(f"Missing floor image in {alt_dir.name}: floor_{fn}.png")
                        elif img.stat().st_size == 0:
                            errors.append(f"Corrupt (0 bytes) floor image in {alt_dir.name}: floor_{fn}.png")
                        else:
                            verified.append(f"{alt_dir.name}/floor_{fn}.png")

    elif check_images:
        # Check single-floor images in 'floors/' or bundle root
        floors_dir = p / "floors"
        target_dir = floors_dir if floors_dir.exists() else p
        for fn in range(1, expected_floors + 1):
            img = target_dir / f"floor_{fn}.png"
            if img.exists() and img.stat().st_size > 0:
                verified.append(str(img.relative_to(p)))

    is_valid = len(errors) == 0
    return ExportIntegrityReport(
        bundle_path=str(p.resolve()),
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        verified_files=verified,
    )
