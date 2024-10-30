import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class BreakDownEntry:
    name: str
    value: float


@dataclasses.dataclass(slots=True)
class RankedLink:
    link: str
    score: float
    breakdown: list[BreakDownEntry]

    def __post_init__(self) -> None:
        if len(self.breakdown) != 0 and isinstance(self.breakdown[0], dict):
            self.breakdown = [BreakDownEntry(**m) for m in self.breakdown]  # type: ignore[arg-type]
