__all__ = ["Document", "Page", "parse_links_from_text", "parser"]

import re

from . import parser
from .document import Document as Document
from .page import Page as Page

RE_SPECIAL_CHAR = re.compile("[^a-zA-Z0-9/]")


def parse_links_from_text(text: str) -> dict[str, set[int]]:
    """
    Tries to parse links from the given text. The returned links are not necessarily valid URLs or may not exist.
    """
    from saadt.util.patterns import RE_HTTP_TEXT, RE_WWW_TEXT

    # put spaces before well-formed urls to make sure we don't break them after removing newlines
    i = 0
    space_idx = []
    for m in RE_HTTP_TEXT.finditer(text):
        index = m.start(1) + i
        text = text[:index] + " " + text[index:]
        space_idx.append(index)
        i += 1

    lines = text.splitlines()
    links: dict[str, set[int]] = {}
    current = ""
    prev_idx = -1
    text_index = 0
    current_breaks = []
    for line in lines:
        text_index += len(line) + 1
        current_breaks.append(len(current))
        if not line:
            continue
        current += line
        for m in RE_WWW_TEXT.finditer(current):
            m_index = text_index - len(current) - 1 + m.start(1) - len([b for b in current_breaks if m.start(1) < b])
            m_index -= len([s for s in space_idx if s < m_index])
            if m.start(1) != 0:
                current = current[m.start(1) :]
                current_breaks = [b - m.start(1) for b in current_breaks if m.start(1) < b]
                prev_idx = -1

            ml = m.group(1)
            if len(ml) <= prev_idx != -1:
                continue
            # If the url ends in a special char, add a second url without that char
            # This could happen in cases where the url is embedded like this: '(http://url),'
            # ')' is valid in an url and only the ',' is removed.
            if RE_SPECIAL_CHAR.fullmatch(ml[-1]) is not None:
                links.setdefault(ml[:-1], set()).add(m_index)
            links.setdefault(ml, set()).add(m_index)
            prev_idx = len(ml)

    return links
