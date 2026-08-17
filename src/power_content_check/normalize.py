"""Text normalisation.

Published labels are PDFs. Extracting text from a PDF introduces line breaks
mid sentence, hyphenated URLs, typographic quotes, non breaking spaces and
column padding. Checks run against a normalised form so that those artefacts of
extraction never become findings against a document.

Normalisation is deliberately lossy in one direction only: it widens what
counts as a match. It never narrows it.
"""

from __future__ import annotations

import re
import unicodedata

_DASHES = "\u002d\u00ad\u2010\u2011\u2012\u2013\u2014\u2015\u2043\u2212\ufe58\ufe63\uff0d"
_SINGLE_QUOTES = "\u2018\u2019\u201a\u201b\u2032\u00b4\u0060"
_DOUBLE_QUOTES = "\u201c\u201d\u201e\u201f\u2033\u00ab\u00bb"
_SPACES = (
    "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u200b\u202f\u205f\u3000\ufeff"
)

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Fold a document into the form the checks match against.

    Dashes become spaces, so "zero-carbon" and "zero carbon" are the same
    string and a URL hyphenated across a line break does not fuse two words.
    An ampersand becomes " and ", so the issued label's "Biomass & Biogas"
    matches the regulation's "Biomass and biogas".
    """
    folded = unicodedata.normalize("NFKC", text)
    for char in _SPACES:
        folded = folded.replace(char, " ")
    for char in _DASHES:
        folded = folded.replace(char, " ")
    for char in _SINGLE_QUOTES:
        folded = folded.replace(char, "'")
    for char in _DOUBLE_QUOTES:
        folded = folded.replace(char, '"')
    folded = folded.replace("&", " and ")
    folded = folded.lower()
    return _WHITESPACE_RUN.sub(" ", folded).strip()


def normalize_lines(text: str) -> list[str]:
    """Normalise each line separately, dropping blank lines.

    Used by the few checks that care about a row of a table rather than the
    document as a whole.
    """
    out = []
    for raw in text.splitlines():
        line = normalize(raw)
        if line:
            out.append(line)
    return out


def contains(haystack_normalized: str, needle: str) -> bool:
    """Substring test where the needle is normalised the same way."""
    return normalize(needle) in haystack_normalized


def _squeezed(normalized: str) -> str:
    return normalized.replace(" ", "")


def contains_ignoring_spaces(haystack_normalized: str, needle: str) -> bool:
    """Substring test that ignores where the extractor put its spaces.

    A PDF can draw one word as more than one text run. A subscript does it:
    the issued labels set the 2 of CO2 as a subscript, and the extractor
    reports "CO", a break, then "2". Normalisation turns that break into a
    space, so the prescribed footnote text of section 1393.1(l)(2) stops
    matching a document that carries it verbatim.

    That space is a fact about how the page was drawn, not about the words the
    document contains, and a deviation reported from it would be a fact about
    this tool wearing the clothes of a fact about someone's label. Comparing
    with the spaces removed on both sides keeps it from becoming one.

    Like everything else in this module, the effect is one directional: it
    widens what counts as a match. Two words that run together in the source
    will also match, which is not a distinction any check here needs to draw.
    """
    return _squeezed(normalize(needle)) in _squeezed(haystack_normalized)
