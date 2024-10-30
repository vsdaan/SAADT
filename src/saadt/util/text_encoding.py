import re

from bs4.dammit import UnicodeDammit
from unidecode import unidecode_expect_ascii, unidecode_expect_nonascii

re_special = re.compile(r"[^\x00-\x7f\w]")
"""Matches non-ascii non-word characters."""


def to_ascii(string: str) -> str:
    return unidecode_expect_ascii(string)


def sanitize(string: str) -> str:
    """
    Replaces non-word, non-ascii characters with their ascii equivalent.
    """
    return re_special.sub(lambda m: unidecode_expect_nonascii(m.group(0)), string)


def unicode(markup: str | bytes, encoding: str | None = None, force_sanitize: bool = False) -> str:
    u = UnicodeDammit(markup, user_encodings=([encoding] if encoding else None), smart_quotes_to="ascii").unicode_markup

    if force_sanitize:
        u = sanitize(u)

    return u
