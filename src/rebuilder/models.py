"""Data models for rebuild results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Build reproducibility status (rebuilderd compatible)."""

    GOOD = "GOOD"  # Successfully reproduced
    BAD = "BAD"  # Failed to reproduce
    UNKNOWN = "UNKWN"  # Unknown/not tested


@dataclass
class Result:
    """Individual build result for a package or image (rebuilderd compatible).

    Based on rebuilderd's PkgRelease structure for compatibility.
    """

    name: str
    version: str
    architecture: str
    suite: str  # e.g., "SNAPSHOT", "23.05.2"
    distro: str  # e.g., "openwrt"
    status: Status
    artifact_url: str = ""  # URL to the original artifact
    build_id: int | None = None
    built_at: str | None = None  # ISO timestamp
    has_diffoscope: bool = False
    has_attestation: bool = False
    diffoscope_url: str | None = None  # URL to diffoscope HTML

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "architecture": self.architecture,
            "suite": self.suite,
            "distro": self.distro,
            "status": self.status.value,
            "artifact_url": self.artifact_url,
            "build_id": self.build_id,
            "built_at": self.built_at,
            "has_diffoscope": self.has_diffoscope,
            "has_attestation": self.has_attestation,
            "diffoscope_url": self.diffoscope_url,
        }


@dataclass
class Results:
    """Container for categorized build results (rebuilderd compatible)."""

    good: list[Result] = field(default_factory=list)
    bad: list[Result] = field(default_factory=list)
    unknown: list[Result] = field(default_factory=list)

    # Status name to attribute mapping
    _status_map: dict[str, str] = field(
        default_factory=lambda: {"GOOD": "good", "BAD": "bad", "UNKWN": "unknown"},
        repr=False,
    )

    def add(self, result: Result) -> None:
        """Add a result to the appropriate category."""
        attr = self._status_map.get(result.status.value, "unknown")
        getattr(self, attr).append(result)

    def total_count(self) -> int:
        """Return total number of results across all categories."""
        return len(self.good) + len(self.bad) + len(self.unknown)

    def stats(self) -> dict[str, int]:
        """Return statistics dictionary (rebuilderd compatible)."""
        return {
            "good": len(self.good),
            "bad": len(self.bad),
            "unknown": len(self.unknown),
        }

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Convert to dictionary for JSON serialization."""
        return {
            "GOOD": [r.to_dict() for r in self.good],
            "BAD": [r.to_dict() for r in self.bad],
            "UNKWN": [r.to_dict() for r in self.unknown],
        }

    # Backwards compatibility aliases
    @property
    def reproducible(self) -> list[Result]:
        """Alias for good (backwards compatibility)."""
        return self.good

    @property
    def unreproducible(self) -> list[Result]:
        """Alias for bad (backwards compatibility)."""
        return self.bad


@dataclass
class Suite:
    """Complete rebuild suite containing packages and images results."""

    packages: Results = field(default_factory=Results)
    images: Results = field(default_factory=Results)

    def add_result(self, category: str, result: Result) -> None:
        """Add a result to the specified category (packages or images)."""
        if category not in ("packages", "images"):
            raise ValueError(f"Invalid category: {category}")
        getattr(self, category).add(result)

    def to_dict(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """Convert to dictionary for JSON serialization."""
        return {
            "packages": self.packages.to_dict(),
            "images": self.images.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Suite:
        """Create a Suite from a dictionary."""
        suite = cls()
        for category in ("packages", "images"):
            if category not in data:
                continue
            for _status_name, items in data[category].items():
                for item in items:
                    result = Result(
                        name=item["name"],
                        version=item["version"],
                        architecture=item.get("architecture", item.get("arch", "")),
                        suite=item.get("suite", ""),
                        distro=item.get("distro", item.get("distribution", "openwrt")),
                        status=Status(item["status"]),
                        artifact_url=item.get("artifact_url", ""),
                        build_id=item.get("build_id"),
                        built_at=item.get("built_at"),
                        has_diffoscope=item.get("has_diffoscope", False),
                        has_attestation=item.get("has_attestation", False),
                        diffoscope_url=item.get("diffoscope_url"),
                    )
                    suite.add_result(category, result)
        return suite
