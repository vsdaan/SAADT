import difflib
from collections.abc import Callable, Iterable
from typing import Generic, TypeVar

from regex import regex

from saadt.util.text_encoding import to_ascii

_T = TypeVar("_T")


class TitleMatcher(Generic[_T]):
    def __init__(self, targets: Iterable[_T] | None, key: Callable[[_T], str] | None = None):
        self.targets: list[_T] | None = None
        self.key: Callable[[_T], str] | None = None
        self.target_patterns: list[regex.Pattern[str]] = []

        self.set_targets(targets, key)

    def _apply_key(self, target: _T) -> str:
        if self.key is None:
            assert isinstance(target, str)
            return target
        return self.key(target)

    @staticmethod
    def title_pattern(title: str, best: bool = True) -> regex.Pattern[str]:
        errs = max(round(len(title) * 0.05), 1)
        flags = regex.I | regex.B if best else regex.I

        return regex.compile(f"({regex.escape(title)}){{e<={errs}}}", flags)

    def set_targets(self, targets: Iterable[_T] | None, key: Callable[[_T], str] | None = None) -> None:
        self.key = key
        if targets is None:
            self.targets = None
            return

        self.targets = []
        self.target_patterns = []
        for _, target in enumerate(targets):
            self.targets.append(target)

            target_str = to_ascii(self._apply_key(target))
            self.target_patterns.append(self.title_pattern(target_str))

    def match(self, candidate: str | _T) -> tuple[_T, regex.Match[str]] | None:
        # filter out papers already in result set
        # Ignores typo's and other mismatches
        # If there is a partial match, check if it is a full partial match
        #   This is basically `paper[0] in title` and vice versa, but with errors.
        if self.targets is None:
            return None

        if isinstance(candidate, str):
            candidate_str = candidate
        else:
            candidate_str = self._apply_key(candidate)

        # Force ascii comparison
        candidate_str = to_ascii(candidate_str)

        matches = []
        errs = max(round(len(candidate_str) * 0.05), 1)
        for i, pattern in enumerate(self.target_patterns):
            m = pattern.match(candidate_str, partial=True)
            if (
                m is not None
                and (m.end() == len(candidate_str) or m.end() == len(self._apply_key(self.targets[i])))
                and sum(m.fuzzy_counts) <= errs
            ):
                if sum(m.fuzzy_counts) == 0:
                    return self.targets[i], m
                matches.append((self.targets[i], m))

        if len(matches) == 0:
            return None

        matches.sort(key=lambda x: sum(x[1].fuzzy_counts))
        return matches[0]

    def unsafe_match(self, candidate: str, cutoff: float = 0.6) -> _T | None:
        if self.targets is None:
            return None

        m = self.match(candidate)
        if m is not None:
            return m[0]

        result = []
        s = difflib.SequenceMatcher()
        s.set_seq2(candidate)
        for x in self.targets:
            s.set_seq1(self._apply_key(x))
            if s.real_quick_ratio() >= cutoff and s.quick_ratio() >= cutoff and s.ratio() >= cutoff:
                result.append((s.ratio(), x))

        if len(result) == 0:
            if ":" in candidate:
                return self.unsafe_match(candidate.split(":")[0], cutoff)
            return None

        return max(result, key=lambda e: e[0])[1]
