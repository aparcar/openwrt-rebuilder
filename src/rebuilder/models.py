"""Data models for rebuild results."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Self


class Status(str, Enum):
    """Build reproducibility status."""

    REPRODUCIBLE = "reproducible"
    UNREPRODUCIBLE = "unreproducible"
    NOTFOUND = "notfound"
    PENDING = "pending"


@dataclass
class Result:
    """Individual build result for a package or image."""

    name: str
    version: str
    arch: str
    distribution: str
    status: Status
    metadata: dict = field(default_factory=dict)
    log: str | None = None
    epoch: int = 0
    diffoscope: str | None = None
    files: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class Results:
    """Container for categorized build results."""

    reproducible: list[Result] = field(default_factory=list)
    pending: list[Result] = field(default_factory=list)
    unreproducible: list[Result] = field(default_factory=list)
    notfound: list[Result] = field(default_factory=list)

    def add(self, result: Result) -> None:
        """Add a result to the appropriate category."""
        getattr(self, result.status.value).append(result)

    def total_count(self) -> int:
        """Return total number of results across all categories."""
        return (
            len(self.reproducible)
            + len(self.pending)
            + len(self.unreproducible)
            + len(self.notfound)
        )

    def stats(self) -> dict[str, int]:
        """Return statistics dictionary."""
        return {
            "reproducible": len(self.reproducible),
            "unreproducible": len(self.unreproducible),
            "notfound": len(self.notfound),
            "pending": len(self.pending),
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "reproducible": [r.to_dict() for r in self.reproducible],
            "pending": [r.to_dict() for r in self.pending],
            "unreproducible": [r.to_dict() for r in self.unreproducible],
            "notfound": [r.to_dict() for r in self.notfound],
        }


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

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "packages": self.packages.to_dict(),
            "images": self.images.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create a Suite from a dictionary."""
        suite = cls()
        for category in ("packages", "images"):
            if category not in data:
                continue
            for status_name, items in data[category].items():
                for item in items:
                    result = Result(
                        name=item["name"],
                        version=item["version"],
                        arch=item["arch"],
                        distribution=item["distribution"],
                        status=Status(item["status"]),
                        metadata=item.get("metadata", {}),
                        log=item.get("log"),
                        epoch=item.get("epoch", 0),
                        diffoscope=item.get("diffoscope"),
                        files=item.get("files", {}),
                    )
                    suite.add_result(category, result)
        return suite
