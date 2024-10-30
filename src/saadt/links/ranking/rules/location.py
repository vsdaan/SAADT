import re
from abc import ABC
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from saadt import pdf
from saadt.links.parsing import ParsedLink
from saadt.links.ranking.rules.base import AbstractRule, RuleContext
from saadt.links.util import safe_parse_url


@dataclass(slots=True)
class LocationRuleContext(RuleContext):
    link: ParsedLink


@dataclass
class LocationBaseRule(AbstractRule[LocationRuleContext], ABC):
    pass


@dataclass
class LocationInPaper(LocationBaseRule):
    """
    Uses dynamic scoring
    """

    score: int = 10

    footnote_pattern: re.Pattern[str] = re.compile(r"\[\S+\]")
    reference_pattern: re.Pattern[str] = re.compile(r"^[^\S\r\n]*(?:\d+.?\s+)?REFERENCES[^\S\r\n]*$", re.I | re.M)

    def _get_cache(self, ctx: LocationRuleContext) -> dict[str, dict[int, str] | pdf.Document]:
        return ctx.root.cache.setdefault(self.__class__.__name__, {})  # type: ignore[no-any-return]

    def _open_document(self, ctx: LocationRuleContext) -> pdf.Document:
        with ctx.root.lock:
            cache = self._get_cache(ctx)

            if (doc := cache.get("doc")) is None:
                assert ctx.root.path is not None
                doc = pdf.Document.new(ctx.root.path.absolute(), pdf.parser.CoordinateParser())
                cache["doc"] = doc

            assert isinstance(doc, pdf.Document)
            return doc

    def _get_page(self, ctx: LocationRuleContext, page_number: int) -> str:
        return next(self._get_pages(ctx, [page_number]))

    def _cache_page(self, ctx: LocationRuleContext, page_cache: dict[int, str], page_number: int) -> str:
        with ctx.root.lock:
            if (page := page_cache.get(page_number)) is not None:
                return page

            doc = self._open_document(ctx)
            page = doc.page(page_number).text()

            page_cache[page_number] = page
            return page

    def _get_pages(self, ctx: LocationRuleContext, page_numbers: Iterable[int]) -> Iterator[str]:
        cache = self._get_cache(ctx)
        page_cache = cache.setdefault("pages", {})
        assert isinstance(page_cache, dict)

        for p in page_numbers:
            yield self._cache_page(ctx, page_cache, p)

    def parse_link_context(self, ctx: LocationRuleContext, text: str, pos: int) -> tuple[int, str, str]:
        section_start, section = self.get_section(text, pos, pos + len(str(ctx.link)))
        link_line_start = section.rfind("\n", 0, pos - section_start) + 1
        link_line = section[link_line_start:].split("\n", maxsplit=1)[0]

        return section_start, section, link_line

    def get_section(self, text: str, _start: int, _end: int) -> tuple[int, str]:
        start = max(0, text.rfind("\n\n\n", 0, _start))
        if start > 0:
            start += 3
        end = text.find("\n\n\n", _end)
        if end < 0:
            end = len(text)

        return start, text[start:end]

    def is_footnote(self, section: str, section_start: int, pos: int) -> bool:
        if len(section[pos - section_start :].splitlines()) > 10:
            return False

        lines = section[: pos - section_start].splitlines()

        for i in range(min(3, len(lines))):
            line = lines[-(i + 1)].strip()
            if line == "":
                break
            if self.footnote_pattern.match(line) is not None:
                return True

        return False

    def is_reference(self, ctx: LocationRuleContext, pos: int) -> bool:
        # 3 pages of references should be enough...
        # Not that this could match a link in the appendix
        page_numbers = reversed(range(max(0, ctx.link.page - 3), ctx.link.page + 1))

        link_page = True
        for text in self._get_pages(ctx, page_numbers):
            if link_page:
                link_page = False
                text = text[:pos]

            if self.reference_pattern.search(text) is not None:
                return True

        return False

    def eval(self, ctx: LocationRuleContext) -> bool:
        if ctx.root.path is None or ctx.root.paper is None:
            return False

        text = self._get_page(ctx, ctx.link.page)

        for pos in ctx.link.locations:
            section_start, section, link_line = self.parse_link_context(ctx, text, pos)

            if self.is_reference(ctx, pos):
                # We can return here as the next iteration is later in the paper
                return False

            if self.is_footnote(section, section_start, pos):
                ctx.score_modifier = 5
                return True

            # should be in a paragraph
            return True

        return False


@dataclass
class LinkParagraphContext(LocationInPaper):
    score: int = 15

    context_pattern: re.Pattern[str] = re.compile(
        r"\b(artifacts|source\b.?code|open\b.?source|our\b\s(?:\w+\s)?("
        r"?:implementation|datasets?|framework|system))\b|\b(available|be found|released|published)\b",
        re.I,
    )

    fix_multiline_pattern: re.Pattern[str] = re.compile(r"-\s+")
    footnote_url_pattern: re.Pattern[str] = re.compile(r"\[(\d{1,2})\]\s*")
    line_pattern: re.Pattern[str] = re.compile(r"(\.\s)(?:\w+\W){2,}")

    def get_link_context(self, text: str, _start: int, _end: int) -> str:
        last_linebreak = text[:_start].rfind("\n")
        if last_linebreak == -1:
            return ""

        idx = _start
        if (match := self.footnote_url_pattern.fullmatch(text[last_linebreak + 1 : _start])) is not None:
            match = re.search(rf"\w+\W?(\[{match.group(1)}\])", text[:last_linebreak])
            if match is not None:
                idx = match.start(1)

        lines = [line for line in text[max(0, idx - 300) : idx].splitlines() if line][-3:]
        if len(lines) == 0:
            return ""

        section = ""
        for line in reversed(lines):
            if (match := self.line_pattern.search(line)) is not None:
                section = f"{line[match.end(1):]} {section}"
                break
            section = f"{line} {section}"

        return self.fix_multiline_pattern.sub("", section.strip())

    def eval(self, ctx: LocationRuleContext) -> bool:
        if ctx.root.path is None or ctx.root.paper is None:
            return False

        text = self._get_page(ctx, ctx.link.page)

        for pos in ctx.link.locations:
            section = self.get_link_context(text, pos, pos + len(ctx.link.link))

            matches = self.context_pattern.findall(section)
            l_matches = [m[0] for m in matches if m[0]]
            r_matches = [m[1] for m in matches if m[1]]
            if len(l_matches) > 0 and len(r_matches) > 0:
                return True
            elif len(r_matches) >= 1 and ctx.root.paper.title.popular_title.lower() in section.lower():
                return True

        return False


class UsenixAppendixLocation(LocationBaseRule):
    score: int = 5

    def eval(self, ctx: LocationRuleContext) -> bool:
        return ctx.link.page == 1


@dataclass
class UsenixAppendixText(LocationBaseRule):
    paper_dir: str
    score: float = 5.0

    _cached_text: tuple[str, str] | None = field(default=None, init=False)

    def eval(self, ctx: LocationRuleContext) -> bool:
        assert ctx.root.paper is not None and ctx.root.path is not None

        if ctx.link.page != 1:
            return False

        pid = ctx.root.paper.id()
        if self._cached_text is None or self._cached_text[0] != pid:
            doc = pdf.Document.new(ctx.root.path.absolute(), pdf.parser.CoordinateParser())
            text = doc.page(1).text()

            self._cached_text = (pid, text)

        text = self._cached_text[1]

        opts = [("Archived", 2), ("Publicly available", 1), ("How to access", 10)]
        for location in ctx.link.locations:
            for marker, max_lines in opts:
                i = text.find(marker)
                if i != -1 and location > i:
                    sub = text[i:location]
                    if sub.count("\n") < max_lines:
                        ctx.score_modifier = 1 - (min(1000, location - i) / 1000.0)
                        return True
        return False


@dataclass
class TitleInUrl(LocationBaseRule):
    score: int = 10

    _sep_rex: re.Pattern[str] = re.compile(r"[:_-]")
    _repl_rex: re.Pattern[str] = re.compile(r"[^\w\s]")

    def eval(self, ctx: LocationRuleContext) -> bool:
        if ctx.root.paper is None:
            return False

        url = safe_parse_url(str(ctx.link))
        if url.host is None:
            return False

        stripped_title = self._repl_rex.sub("", self._sep_rex.sub(" ", ctx.root.paper.title.popular_title.lower()))
        title_parts = [p for p in stripped_title.split() if len(p) > 1]
        if len(title_parts) == 0:
            return False

        if len(title_parts) == 1 and len(title_parts[0]) <= 3:
            return False

        target = f"{url.host}{url.path or ""}".lower()
        if all(part in target for part in title_parts):
            return True
        return False
