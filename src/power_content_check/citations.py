"""Published sources this tool cites.

Every entry here was fetched from the publisher and read. Nothing in this file
is paraphrased from memory. If a requirement is not in one of these documents,
there is no check for it.

The ``quote`` on each citation is the operative language, transcribed from the
source. Long quotes are trimmed at a sentence boundary and never reworded.
"""

from __future__ import annotations

from .model import Citation, Source

RETRIEVED = "2026-08-17"

#: California Code of Regulations, title 20, division 2, chapter 3, article 5.
#: The PDF the California Energy Commission publishes as the operative text of
#: the Power Source Disclosure regulations.
PSD_REGULATIONS = Source(
    key="ccr-t20-art5",
    title=(
        "California Code of Regulations, title 20, division 2, chapter 3, "
        "article 5 (Power Source Disclosure), sections 1391 through 1394"
    ),
    publisher="California Energy Commission",
    url="https://efiling.energy.ca.gov/GetDocument.aspx?tn=264974&DocumentContentId=101752",
    retrieved=RETRIEVED,
    effective="2025-06-18",
)

#: The Power Content Labels the Energy Commission itself issues. Cited only for
#: checks whose basis is the issued format rather than a sentence of the
#: regulation, which section 1393.1(i) permits the Energy Commission to set and
#: forbids a retail supplier to alter.
CEC_ISSUED_LABELS = Source(
    key="cec-issued-labels-2024",
    title="Annual Power Content Labels for 2024, as issued by the California Energy Commission",
    publisher="California Energy Commission",
    url=(
        "https://www.energy.ca.gov/programs-and-topics/programs/"
        "power-source-disclosure-program/power-content-label/annual-power-5"
    ),
    retrieved=RETRIEVED,
    effective=None,
)

#: The authorising statute. Recorded so the chain of authority is visible; no
#: check cites it on its own, because the regulation is the more specific text.
PUC_398_4 = Source(
    key="ca-puc-398.4",
    title="California Public Utilities Code section 398.4",
    publisher="California Legislative Counsel",
    url=(
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml"
        "?lawCode=PUC&sectionNum=398.4"
    ),
    retrieved=RETRIEVED,
    effective=None,
)

RULESET_ID = "ccr-t20-art5@2025-06-18"
RULESET_EFFECTIVE = "2025-06-18"


def reg(locator: str, quote: str) -> Citation:
    """Cite the Power Source Disclosure regulations."""
    return Citation(source=PSD_REGULATIONS, locator=locator, quote=quote)


def issued_format(locator: str, quote: str) -> Citation:
    """Cite the label format the Energy Commission issues under section 1393.1(i)."""
    return Citation(source=CEC_ISSUED_LABELS, locator=locator, quote=quote)


#: Reproduced on every report. This tool is not a compliance determination and
#: says so in its own output, not only in the README.
NOTICE = (
    "This tool checks a document against the published Power Content Label format. "
    "It makes no judgment about any supplier's power mix, its performance, or its "
    "compliance status, and it does not rank suppliers. Under California Code of "
    "Regulations, title 20, section 1393.1(i), the California Energy Commission "
    "generates the label or supplies the template and the retail supplier may not "
    "alter the format, so a reported deviation is a property of the document and is "
    "not evidence of anything a named supplier did. This tool is not affiliated with, "
    "endorsed by, or approved by the California Energy Commission or any utility."
)
