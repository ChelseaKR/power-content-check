"""The check catalog.

Ground rules for this file, in order of importance:

1. No check enforces a requirement that is not in a cited published document.
   If the regulation does not say it, there is no check for it. Where a check
   enforces the format the California Energy Commission itself issues rather
   than a sentence of regulatory text, its basis is TEMPLATE_FORMAT and it says
   so.

2. A check that cannot measure something returns NOT_EVALUATED. It never
   returns CONFORMS as a default. The engine also converts any exception raised
   here into NOT_EVALUATED, so a crash cannot become a pass.

3. Check identifiers are permanent. PCL001 means what it meant on the day it
   was added, forever. Retiring a check leaves the identifier retired, never
   recycled.

4. Findings describe the document. They do not describe the supplier. A
   deviation from the issued format is not a compliance determination and the
   wording must not read like one.

5. Every deviation says what the tool looked at. A check here reports that
   something is absent from extracted text, which is a smaller claim than
   saying it is absent from the document. :func:`_bad` attaches the document's
   extraction basis to every deviation so that the smaller claim is the one on
   the page.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .citations import issued_format, reg
from .extract import LabelDocument
from .model import Basis, Blocker, CheckResult, CheckSpec, Status

# ---------------------------------------------------------------------------
# matching helpers
# ---------------------------------------------------------------------------

_PERCENT = r"\d{1,3}(?:\.\d+)?\s?%"
_LEADING_JUNK = re.compile(r"^[^0-9a-z]+")
_PHONE = re.compile(
    r"(?<![0-9])(?:\+?1[\s.\-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.\-])\d{3}[\s.\-]\d{4}(?![0-9])"
)
_DOMAIN = re.compile(
    r"(?:https?://)?(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+"
    r"(?:com|org|net|gov|edu|us|coop|io|info|biz|energy)\b"
)
_TOTAL_ROW = re.compile(rf"^total\s+((?:{_PERCENT}\s*)+)$")
_YEAR_TITLE = re.compile(r"\b((?:19|20)\d{2})\s+power content label\b")
_UNSPECIFIED_ANNOTATION = re.compile(
    r"unspecified power\s*[:(]?\s*primarily\s+([a-z ]+?)"
    r"(?:\s*\)|(?=\s*\d)|(?=\s*%)|(?=[.,;:]|$))"
)


def _row_label(line: str) -> str:
    """Strip a leading bullet or other decoration from a normalised line."""
    return _LEADING_JUNK.sub("", line)


def _has_row(doc: LabelDocument, term: str) -> bool:
    """True when ``term`` begins a row of the label."""
    return any(_row_label(line).startswith(term) for line in doc.normalized_lines)


def _has_labelled_figure(doc: LabelDocument, term: str) -> bool:
    """True when ``term`` is immediately followed by a percentage figure.

    The intervening characters may not contain letters, which keeps prose that
    merely mentions a fuel type from satisfying a check that is about a row of
    the table.
    """
    pattern = rf"\b{re.escape(term)}\b[^a-z]{{0,40}}{_PERCENT}"
    return re.search(pattern, doc.normalized) is not None


def _fuel_row_present(doc: LabelDocument, term: str) -> tuple[bool, str]:
    if _has_row(doc, term):
        return True, "row"
    if _has_labelled_figure(doc, term):
        return True, "figure"
    return False, "absent"


def _domains(doc: LabelDocument) -> list[str]:
    text = doc.raw_text.lower()
    return [m.group(0) for m in _DOMAIN.finditer(text)]


def _phones(doc: LabelDocument) -> list[str]:
    found = [m.group(0).strip() for m in _PHONE.finditer(doc.raw_text)]
    normalised = {re.sub(r"[^0-9]", "", p)[-10:] for p in found}
    return sorted(normalised)


# ---------------------------------------------------------------------------
# the fuel type categories of section 1393.1(c)(1)
# ---------------------------------------------------------------------------

#: Subparagraphs (A) through (J), transcribed from the regulation. The
#: normaliser turns the issued label's "Biomass & Biogas" into
#: "biomass and biogas", so one spelling covers both renderings.
REQUIRED_FUEL_TYPES: tuple[tuple[str, str], ...] = (
    ("A", "biomass and biogas"),
    ("B", "geothermal"),
    ("C", "eligible hydroelectric"),
    ("D", "solar"),
    ("E", "wind"),
    ("F", "large hydroelectric"),
    ("G", "nuclear"),
    ("H", "natural gas"),
    ("I", "coal and petroleum"),
    ("J", "unspecified power"),
)

#: Subparagraphs (K) and (L). The regulation qualifies both with
#: "if applicable", so their absence is not a deviation and this tool does not
#: attempt to decide whether they applied.
CONDITIONAL_FUEL_TYPES: tuple[tuple[str, str], ...] = (
    ("K", "emerging technologies"),
    ("L", "other"),
)

#: The two resource groups of section 1393.1(c)(2) whose names section
#: 1393.1(c)(7) requires the unspecified power annotation to choose between.
GROUP_NAMES = ("fossil fuels", "renewables and zero carbon resources")

#: Renderings accepted for the separate statewide disclosure required by
#: section 1393.1(a) and named "total California loss-adjusted load" in section
#: 1393.1(c)(1). The Energy Commission's issued labels render it as
#: "CA Utility Average", so both the regulation's wording and the issued
#: wording are accepted. Section 1393.1(a)(3) renames the quantity for labels
#: from 2026 on ("California's total loss-adjusted load"), so the
#: regulation's own 2026 phrasing is accepted too, ahead of any label that
#: carries it.
STATEWIDE_RENDERINGS = (
    "total california loss adjusted load",
    "california loss adjusted load",
    "total california system electricity",
    "california system electricity",
    "ca utility average",
    "california utility average",
    "california's total loss adjusted load",
)


@dataclass(frozen=True)
class CheckContext:
    """Facts a check needs that the document cannot supply on its own."""

    supplier_name: str | None = None


CheckFn = Callable[[LabelDocument, CheckContext], CheckResult]


def _with_basis(doc: LabelDocument, detail: str | None) -> str:
    """Attach what the tool was able to look at to what it concluded."""
    return " ".join(part for part in (detail, doc.extraction_basis) if part)


def _ok(check_id: str, finding: str, detail: str | None = None) -> CheckResult:
    return CheckResult(check_id, Status.CONFORMS, finding, detail)


def _bad(doc: LabelDocument, check_id: str, finding: str, detail: str | None = None) -> CheckResult:
    """A deviation, carrying the basis on which the tool looked.

    Every deviation this tool reports is the absence of something from text it
    could read. Whether that absence is a property of the document or a limit
    of extraction depends on what else the document is carrying, so the answer
    travels with the finding rather than living only in the documentation.
    """
    return CheckResult(check_id, Status.DOES_NOT_CONFORM, finding, _with_basis(doc, detail))


def _unknown(check_id: str, finding: str, detail: str | None = None) -> CheckResult:
    return CheckResult(check_id, Status.NOT_EVALUATED, finding, detail)


# ---------------------------------------------------------------------------
# implemented checks
# ---------------------------------------------------------------------------


def _pcl001(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if not ctx.supplier_name:
        return _unknown(
            "PCL001",
            "Not evaluated: no supplier name was supplied to compare against.",
            "Pass --supplier-name to check that the label carries the company name.",
        )
        # The tool will not guess which line of a label is the company name.
    from .normalize import normalize

    wanted = normalize(ctx.supplier_name)
    if wanted and wanted in doc.normalized:
        return _ok("PCL001", f"The label carries the company name '{ctx.supplier_name}'.")
    return _bad(
        doc,
        "PCL001",
        f"The company name '{ctx.supplier_name}' does not appear in the extracted text.",
        "Section 1393.1(c)(4) lists the retail supplier's company name among the "
        "contents each label discloses.",
    )


def _pcl002(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    phones = _phones(doc)
    if len(phones) >= 2:
        return _ok("PCL002", f"{len(phones)} distinct telephone numbers appear on the label.")
    if len(phones) == 1:
        return _bad(
            doc,
            "PCL002",
            "Only one telephone number appears in the extracted text.",
            "Section 1393.1(c)(4) lists a telephone number for the retail supplier "
            "and a telephone number for the Energy Commission, which is two numbers.",
        )
    return _bad(
        doc,
        "PCL002",
        "No telephone number appears in the extracted text.",
        "Section 1393.1(c)(4) lists a telephone number for the retail supplier "
        "and a telephone number for the Energy Commission.",
    )


def _pcl003(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    others = [d for d in _domains(doc) if "energy.ca.gov" not in d]
    if others:
        return _ok(
            "PCL003",
            "A web address other than the Energy Commission's appears on the label.",
            f"Observed: {', '.join(sorted(set(others))[:5])}",
        )
    return _bad(
        doc,
        "PCL003",
        "No web address for the retail supplier appears in the extracted text.",
        "Section 1393.1(c)(4) lists the retail supplier's website address among the "
        "contents each label discloses.",
    )


def _pcl004(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if "energy commission" in doc.normalized:
        return _ok("PCL004", "The label names the Energy Commission.")
    observed = []
    if re.search(r"\bcec\b", doc.normalized):
        observed.append("the abbreviation 'CEC'")
    if any("energy.ca.gov" in d for d in _domains(doc)):
        observed.append("an energy.ca.gov web address")
    seen = f"Present instead: {', '.join(observed)}. " if observed else ""
    return _bad(
        doc,
        "PCL004",
        "The words 'Energy Commission' do not appear in the extracted text.",
        "Section 1393.1(c)(4) lists the name of the Energy Commission among the "
        "contents each label discloses, and section 1391 defines 'Energy Commission' "
        "to mean the State Energy Resources Conservation and Development Commission. "
        f"{seen}"
        "The regulation nowhere defines 'CEC', so this check does not read the "
        "abbreviation as the name, and the web address is checked separately by PCL005.",
    )


def _pcl005(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if any("energy.ca.gov" in d for d in _domains(doc)):
        return _ok("PCL005", "The label carries an energy.ca.gov web address.")
    return _bad(
        doc,
        "PCL005",
        "No Energy Commission web address appears in the extracted text.",
        "Section 1393.1(c)(4) lists the website address of the Energy Commission "
        "among the contents each label discloses.",
    )


def _pcl006(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    missing: list[str] = []
    found: list[str] = []
    for letter, term in REQUIRED_FUEL_TYPES:
        present, _how = _fuel_row_present(doc, term)
        (found if present else missing).append(f"({letter}) {term}")

    conditional = [
        f"({letter}) {term}"
        for letter, term in CONDITIONAL_FUEL_TYPES
        if _fuel_row_present(doc, term)[0]
    ]
    detail = (
        f"Conditional categories present: {', '.join(conditional) or 'none'}. "
        "Subparagraphs (K) and (L) are qualified 'if applicable' and are never "
        "reported as missing."
    )
    if missing:
        return _bad(
            doc,
            "PCL006",
            f"{len(missing)} of the 10 unconditional fuel type categories are absent "
            f"from the extracted text: {', '.join(missing)}.",
            detail,
        )
    return _ok("PCL006", "All 10 unconditional fuel type categories appear on the label.", detail)


def _pcl007(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if "renewables and zero carbon resources" in doc.normalized:
        return _ok("PCL007", "The 'Renewables and Zero-Carbon Resources' group appears.")
    return _bad(
        doc,
        "PCL007",
        "The 'Renewables and Zero-Carbon Resources' group does not appear in the extracted text.",
        "Section 1393.1(c)(2)(A) requires the fuel mix to be displayed in this group.",
    )


def _pcl008(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if re.search(r"rps\s+eligible\s+renewables", doc.normalized):
        return _ok("PCL008", "RPS-eligible renewables appear as a named subcategory.")
    return _bad(
        doc,
        "PCL008",
        "RPS-eligible renewables do not appear as a named subcategory in the extracted text.",
        "Section 1393.1(c)(2)(A) provides that RPS-eligible renewables shall be "
        "identified as a subcategory of the Renewables and Zero-Carbon Resources group.",
    )


def _pcl009(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if "fossil fuels" in doc.normalized:
        return _ok("PCL009", "The 'Fossil Fuels' group appears.")
    return _bad(
        doc,
        "PCL009",
        "The 'Fossil Fuels' group does not appear in the extracted text.",
        "Section 1393.1(c)(2)(B) requires the fuel mix to be displayed in this group.",
    )


def _pcl010(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    text = doc.normalized
    if "greenhouse gas emissions intensity" not in text and "ghg emissions intensity" not in text:
        return _bad(
            doc,
            "PCL010",
            "No greenhouse gas emissions intensity disclosure appears in the extracted text.",
            "Section 1393.1(c)(3) requires the GHG emissions intensity of each "
            "electricity portfolio to be disclosed.",
        )
    has_mass = re.search(r"\b(lbs|lb|pounds)\b", text) is not None
    has_co2e = "co2e" in text
    has_rate = re.search(r"per\s+megawatt\s+hour|/\s?mwh|per\s+mwh", text) is not None
    if has_mass and has_co2e and has_rate:
        return _ok(
            "PCL010",
            "The GHG emissions intensity is stated in pounds of CO2e per megawatt hour.",
        )
    missing = [
        name
        for name, present in (
            ("a pounds unit", has_mass),
            ("CO2e", has_co2e),
            ("a per megawatt hour denominator", has_rate),
        )
        if not present
    ]
    return _bad(
        doc,
        "PCL010",
        "The GHG emissions intensity is present but its units are not fully stated: "
        f"missing {', '.join(missing)}.",
        "Section 1393.1(c)(3) requires the figure to be expressed in pounds of CO2e "
        "per megawatt hour.",
    )


def _pcl011(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if re.search(r"retired\s+unbundled\s+recs?|unbundled\s+recs?\s+retired", doc.normalized):
        return _ok("PCL011", "The label discloses retired unbundled RECs.")
    return _bad(
        doc,
        "PCL011",
        "No disclosure of retired unbundled RECs appears in the extracted text.",
        "Section 1393.1(c)(5) requires the quantity of unbundled RECs retired in "
        "association with each electricity portfolio, expressed as a percentage of "
        "retail sales. A mention of unbundled RECs in the footnote required by "
        "section 1393.1(l)(1) does not satisfy this.",
    )


def _pcl012(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    match = _UNSPECIFIED_ANNOTATION.search(doc.normalized)
    if match:
        group = match.group(1).strip()
        if group in GROUP_NAMES:
            return _ok(
                "PCL012",
                f"Unspecified power is annotated as primarily {group}.",
            )
        return _bad(
            doc,
            "PCL012",
            f"Unspecified power is annotated as primarily '{group}', which is not one "
            "of the two resource groups.",
            "Section 1393.1(c)(7) requires the annotation to identify either "
            "'Fossil Fuels' or 'Renewables and Zero-Carbon Resources'.",
        )
    return _bad(
        doc,
        "PCL012",
        "The display of unspecified power is not annotated with its predominant resource "
        "group anywhere in the extracted text.",
        "Section 1393.1(c)(7) requires the display of unspecified power to be "
        "annotated to identify whether it was provided primarily by 'Fossil Fuels' "
        "or 'Renewables and Zero-Carbon Resources'.",
    )


def _footnote_check(check_id: str, lead: str, ordinal: str) -> CheckFn:
    def run(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
        from .normalize import contains_ignoring_spaces

        if contains_ignoring_spaces(doc.normalized, lead):
            return _ok(check_id, f"The footnote required by section 1393.1(l)({ordinal}) appears.")
        return _bad(
            doc,
            check_id,
            f"The footnote required by section 1393.1(l)({ordinal}) does not appear in "
            "the extracted text.",
            f"The check matches the opening clause of the prescribed text: '{lead}'. "
            "It does not compare the whole footnote word for word, and it ignores "
            "where the extractor put its spaces, so a subscript or any other split "
            "text run is not read as missing words.",
        )

    return run


_FOOTNOTE_1_LEAD = "This label does not reflect compliance with the Renewables Portfolio Standard"
_FOOTNOTE_2_LEAD = (
    "GHG intensity figures exclude biogenic CO2 and emissions from geothermal sources"
)
_FOOTNOTE_3_LEAD = (
    "Unspecified power is electricity purchased from a genericized pool on the open market"
)

_pcl013 = _footnote_check("PCL013", _FOOTNOTE_1_LEAD, "1")
_pcl014 = _footnote_check("PCL014", _FOOTNOTE_2_LEAD, "2")
_pcl015 = _footnote_check("PCL015", _FOOTNOTE_3_LEAD, "3")


def _all_words_present(doc: LabelDocument, phrase: str) -> bool:
    """True when every word of ``phrase`` appears somewhere, in any order."""
    return all(
        re.search(rf"\b{re.escape(word)}\b", doc.normalized) is not None for word in phrase.split()
    )


def _in_a_reconstructed_cell(doc: LabelDocument, renderings: list[str]) -> str | None:
    """The first rendering that sits whole inside one reconstructed cell.

    Reading a PDF column by column instead of line by line is the one use ADR
    0007 left open for position, and this is the only place in the tool that
    uses it. It is reached only from the branch below, which reports
    NOT_EVALUATED, so geometry can turn "the tool cannot tell" into "the tool
    found it" and can do nothing else. It cannot produce a deviation, because
    the deviation is returned before it is consulted for any document whose
    text layer lacks the words entirely.
    """
    from .normalize import contains_ignoring_spaces

    if not doc.cells:
        return None
    for rendering in renderings:
        if any(contains_ignoring_spaces(cell, rendering) for cell in doc.cells):
            return rendering
    return None


def _pcl016(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    from .normalize import contains_ignoring_spaces

    for rendering in STATEWIDE_RENDERINGS:
        if contains_ignoring_spaces(doc.normalized, rendering):
            return _ok(
                "PCL016",
                "The label separately discloses the statewide figures.",
                f"Matched the rendering '{rendering}'.",
            )

    # A column heading is not prose. On the labels the Energy Commission
    # issues, a heading too long for its column wraps onto a second line, and
    # extraction reads across the wrap, so the words of one heading arrive with
    # the words of its neighbour inside them. A document that carries the
    # heading and a document that lacks it then look the same to a substring
    # test, and the tool is not entitled to pick the accusing one.
    scattered = [r for r in STATEWIDE_RENDERINGS if _all_words_present(doc, r)]
    if scattered:
        recovered = _in_a_reconstructed_cell(doc, scattered)
        if recovered:
            return _ok(
                "PCL016",
                "The label separately discloses the statewide figures.",
                f"Matched the rendering '{recovered}' in a column read down the page "
                "rather than across it. The words are out of order in the text layer "
                "because the heading wraps onto a second line and extraction reads "
                "across the wrap; the position of each word on the page puts them back "
                "in the same cell.",
            )
        return _unknown(
            "PCL016",
            "Not evaluated: every word of the accepted rendering "
            f"'{scattered[0]}' appears, but not together.",
            _with_basis(
                doc,
                "Extraction does not preserve the order of a column heading that wraps "
                "onto a second line, so words belonging to the heading beside it can "
                "arrive in the middle of this one. Reading the page column by column "
                "did not put the rendering back together either, or this document "
                "carries no recoverable geometry. The tool cannot tell that apart from "
                "a heading that is absent, so it reports neither.",
            ),
        )

    return _bad(
        doc,
        "PCL016",
        "No separate statewide disclosure appears in the extracted text.",
        "Section 1393.1(a) requires the fuel mix and GHG emissions intensity of "
        "total California system electricity to be disclosed separately, and "
        "section 1393.1(c)(1) names the quantity total California loss-adjusted "
        "load. Accepted renderings, which include the wording used on the labels "
        f"the Energy Commission issues, are: {', '.join(STATEWIDE_RENDERINGS)}.",
    )


def _pcl017(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    match = _YEAR_TITLE.search(doc.normalized)
    if match:
        return _ok("PCL017", f"The label identifies its data year as {match.group(1)}.")
    return _bad(
        doc,
        "PCL017",
        "The extracted text does not identify the calendar year the label covers.",
        "Section 1393.1(a) scopes each label to the previous calendar year, and the "
        "labels the Energy Commission issues under section 1393.1(i) carry the year "
        "in the title, in the form '2024 POWER CONTENT LABEL'.",
    )


def _pcl018(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    for line in doc.normalized_lines:
        match = _TOTAL_ROW.match(_row_label(line))
        if not match:
            continue
        values = [float(v.rstrip("% ").strip()) for v in re.findall(_PERCENT, match.group(1))]
        off = [v for v in values if v != 100.0]
        if off:
            return _bad(
                doc,
                "PCL018",
                f"A displayed column total is not 100 percent: {off}.",
                "Section 1392(b)(1) expresses the fuel mix as percentages of the "
                "portfolio's retail sales, and the labels the Energy Commission "
                "issues display a total row of 100 percent for every column. This "
                "reads the total the label itself displays. It does not add up the "
                "rows above it, for the reason recorded against PCL025.",
            )
        return _ok(
            "PCL018",
            f"All {len(values)} displayed column totals are 100 percent.",
        )
    return _unknown(
        "PCL018",
        "Not evaluated: no total row was located in the extracted text.",
        _with_basis(
            doc,
            "Without a total row there is nothing to compare, and this tool does not "
            "recompute a supplier's fuel mix. See PCL025.",
        ),
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredCheck:
    spec: CheckSpec
    run: CheckFn | None


def _implemented(
    check_id: str,
    title: str,
    citation_locator: str,
    quote: str,
    what: str,
    fn: CheckFn,
    basis: Basis = Basis.REGULATION_TEXT,
    issued: bool = False,
) -> RegisteredCheck:
    cite = issued_format(citation_locator, quote) if issued else reg(citation_locator, quote)
    return RegisteredCheck(
        spec=CheckSpec(
            id=check_id,
            title=title,
            citation=cite,
            basis=basis,
            implemented=True,
            what_it_looks_for=what,
        ),
        run=fn,
    )


def _registered_only(
    check_id: str,
    title: str,
    citation_locator: str,
    quote: str,
    reason: str,
    blocker: Blocker,
    basis: Basis = Basis.REGULATION_TEXT,
) -> RegisteredCheck:
    return RegisteredCheck(
        spec=CheckSpec(
            id=check_id,
            title=title,
            citation=reg(citation_locator, quote),
            basis=basis,
            implemented=False,
            what_it_looks_for="Nothing. This check is registered but enforces no rule.",
            unimplemented_reason=reason,
            blocker=blocker,
        ),
        run=None,
    )


CHECKS: tuple[RegisteredCheck, ...] = (
    _implemented(
        "PCL001",
        "Retail supplier company name",
        "section 1393.1(c)(4)",
        "The retail supplier's company name, phone number, and website address, and "
        "the name, phone number, and website address of the Energy Commission.",
        "The supplier name given on the command line appears somewhere in the label text.",
        _pcl001,
    ),
    _implemented(
        "PCL002",
        "Telephone numbers",
        "section 1393.1(c)(4)",
        "The retail supplier's company name, phone number, and website address, and "
        "the name, phone number, and website address of the Energy Commission.",
        "At least two distinct North American telephone numbers appear in the label text.",
        _pcl002,
    ),
    _implemented(
        "PCL003",
        "Retail supplier website address",
        "section 1393.1(c)(4)",
        "The retail supplier's company name, phone number, and website address, and "
        "the name, phone number, and website address of the Energy Commission.",
        "At least one web address that is not on energy.ca.gov appears in the label text.",
        _pcl003,
    ),
    _implemented(
        "PCL004",
        "Energy Commission named",
        "section 1393.1(c)(4)",
        "The retail supplier's company name, phone number, and website address, and "
        "the name, phone number, and website address of the Energy Commission.",
        "The words 'Energy Commission' appear in the label text.",
        _pcl004,
    ),
    _implemented(
        "PCL005",
        "Energy Commission website address",
        "section 1393.1(c)(4)",
        "The retail supplier's company name, phone number, and website address, and "
        "the name, phone number, and website address of the Energy Commission.",
        "An energy.ca.gov web address appears in the label text.",
        _pcl005,
    ),
    _implemented(
        "PCL006",
        "Fuel type categories",
        "section 1393.1(c)(1)",
        "Fuel mix information of each electricity portfolio, total power content, and "
        "of total California loss-adjusted load shall be provided using the fuel type "
        "categories: (A) Biomass and biogas (B) Geothermal (C) Eligible hydroelectric "
        "(D) Solar (E) Wind (F) Large hydroelectric (G) Nuclear (H) Natural gas "
        "(I) Coal and petroleum (J) Unspecified power (K) Emerging technologies, if "
        "applicable (L) Other, if applicable.",
        "Each of subparagraphs (A) through (J) begins a row, or is followed by a "
        "percentage figure. (K) and (L) are qualified 'if applicable' and are "
        "reported but never required.",
        _pcl006,
    ),
    _implemented(
        "PCL007",
        "Renewables and Zero-Carbon Resources group",
        "section 1393.1(c)(2)(A)",
        "Renewables and Zero-Carbon Resources from fuel types identified in Section "
        "1393.1(c)(1)(A) through (G). RPS-eligible renewables shall be identified as a "
        "subcategory of this group.",
        "The group name appears in the label text.",
        _pcl007,
    ),
    _implemented(
        "PCL008",
        "RPS-eligible renewables subcategory",
        "section 1393.1(c)(2)(A)",
        "RPS-eligible renewables shall be identified as a subcategory of this group.",
        "The words 'RPS eligible renewables' appear in the label text.",
        _pcl008,
    ),
    _implemented(
        "PCL009",
        "Fossil Fuels group",
        "section 1393.1(c)(2)(B)",
        "Fossil Fuels from fuel types identified in Section 1393.1(c)(1)(H) through (I).",
        "The group name appears in the label text.",
        _pcl009,
    ),
    _implemented(
        "PCL010",
        "GHG emissions intensity units",
        "section 1393.1(c)(3)",
        "GHG emissions intensity of each electricity portfolio, of total power content, "
        "and of total California loss-adjusted load in accordance with the calculation "
        "method provided in section 1392(b), expressed in pounds of CO2e per megawatt hour.",
        "A greenhouse gas emissions intensity disclosure appears and states a pounds "
        "unit, CO2e, and a per megawatt hour denominator. The value itself is not checked.",
        _pcl010,
    ),
    _implemented(
        "PCL011",
        "Retired unbundled RECs",
        "section 1393.1(c)(5)",
        "Quantity of unbundled RECs retired in association with each electricity "
        "portfolio, expressed as a percentage of retail sales.",
        "The label states that unbundled RECs were retired, as distinct from merely "
        "mentioning unbundled RECs in the prescribed footnote.",
        _pcl011,
    ),
    _implemented(
        "PCL012",
        "Unspecified power annotation",
        "section 1393.1(c)(7)",
        "The display of unspecified power on the power content label shall be annotated "
        "to identify whether the unspecified power was provided primarily by either "
        "'Fossil Fuels' or 'Renewables and Zero-Carbon Resources' as those groups are "
        "described in 1393.1(c)(2), whichever group was greater for the previous year.",
        "The unspecified power display is annotated 'primarily' one of the two group names.",
        _pcl012,
    ),
    _implemented(
        "PCL013",
        "Footnote: RPS compliance disclaimer",
        "section 1393.1(l)(1)",
        "This label does not reflect compliance with the Renewables Portfolio Standard "
        "(RPS), which measures the use of tracking instruments called Renewable Energy "
        "Credits (RECs) over the course of multi-year compliance periods.",
        "The opening clause of the prescribed footnote appears in the label text.",
        _pcl013,
    ),
    _implemented(
        "PCL014",
        "Footnote: GHG exclusions",
        "section 1393.1(l)(2)",
        "GHG intensity figures exclude biogenic CO2 and emissions from geothermal "
        "sources and grandfathered imports of firmed-and-shaped energy.",
        "The opening clause of the prescribed footnote appears in the label text.",
        _pcl014,
    ),
    _implemented(
        "PCL015",
        "Footnote: unspecified power definition",
        "section 1393.1(l)(3)",
        "Unspecified power is electricity purchased from a genericized pool on the open market.",
        "The prescribed footnote text appears in the label text.",
        _pcl015,
    ),
    _implemented(
        "PCL016",
        "Separate statewide disclosure",
        "section 1393.1(a) and section 1393.1(c)(1)",
        "Each retail supplier shall provide to consumers a power content label that "
        "discloses the fuel mix and GHG emissions intensity of each electricity "
        "portfolio that was sold during the previous calendar year, and separately "
        "disclose the fuel mix and GHG emissions intensity of total California system "
        "electricity.",
        "One of the accepted renderings of the statewide column heading appears. The "
        "accepted list includes the wording used on the labels the Energy Commission "
        "issues, because a supplier may not alter that format. Where the words are all "
        "present but not together, the page is read column by column before the check "
        "gives up, because a heading that wraps arrives out of order in a text layer.",
        _pcl016,
    ),
    _implemented(
        "PCL017",
        "Data year identified",
        "section 1393.1(i)",
        "The Energy Commission shall generate power content labels on behalf of each "
        "retail supplier or provide a power content label template on the Energy "
        "Commission website for each retail supplier to generate its power content "
        "label. The format of the power content label may not be altered by the retail "
        "supplier.",
        "A four digit year immediately precedes the words 'power content label'.",
        _pcl017,
        basis=Basis.TEMPLATE_FORMAT,
        issued=True,
    ),
    _implemented(
        "PCL018",
        "Displayed column totals",
        "section 1393.1(i)",
        "The format of the power content label may not be altered by the retail supplier.",
        "If a total row is present, every percentage on it is 100. If no total row is "
        "found the check is not evaluated, because this tool does not recompute a mix.",
        _pcl018,
        basis=Basis.TEMPLATE_FORMAT,
        issued=True,
    ),
    # -----------------------------------------------------------------------
    # Registered, enforcing nothing. Each of these is a real requirement in the
    # cited source that this tool does not measure. They appear in every report
    # as NOT_EVALUATED so that the gap is visible rather than implied by
    # silence.
    #
    # Every one carries a Blocker. PERMANENT means no version of this tool that
    # reads the document it is handed can decide the requirement. CONDITIONAL
    # means the reason names something that could change. The point of the
    # distinction is that a future reader can stop reopening the permanent ones.
    # -----------------------------------------------------------------------
    _registered_only(
        "PCL019",
        "All label information in one place",
        "section 1393.1(h)",
        "All information contained in the power content label shall appear in one "
        "place without other intervening material.",
        "Subdivision (h) governs where the label sits inside the promotional materials "
        "it is published in, and subdivisions (h)(1) and (h)(2) turn on how many pages "
        "those materials run to and on which page a customer meets the label first. A "
        "file holding the label alone cannot exhibit the deviation, and this tool is "
        "handed a file rather than a publication, so it cannot tell which of the two it "
        "has. Deciding what counts as intervening material is a second, separate "
        "judgment about visual layout. The published text nowhere equates 'one place' "
        "with one page, so a tool that reported a label spread over two pages of a file "
        "would be enforcing an equivalence it wrote itself.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL020",
        "Mixed portfolio footnote",
        "section 1393.1(f)",
        "If individual customers are served by a mixture of electricity portfolios, "
        "the power content label shall include a footnote on the power content label "
        "stating that some customers of the retail supplier may be served by more "
        "than one electricity portfolio.",
        "Whether any customer is served by a mixture of portfolios is a fact about the "
        "supplier's service, not about the document. The tool cannot establish whether "
        "the requirement was triggered, so it will not report either way. Presence is "
        "visible and absence is not: one of the twenty four published 2024 labels this "
        "project read carries the footnote in the words subdivision (f) describes. A "
        "check built on that asymmetry could only ever confirm, never find a deviation, "
        "and would add to the implemented count without adding any ability to find "
        "anything, so it was considered and refused.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL021",
        "Attribution of contact details",
        "section 1393.1(c)(4)",
        "The retail supplier's company name, phone number, and website address, and "
        "the name, phone number, and website address of the Energy Commission.",
        "PCL002, PCL003 and PCL005 count contact details but cannot say which belongs "
        "to the supplier and which to the Energy Commission. Positional extraction was "
        "assessed as the way to settle that and does not settle it. Coordinates give "
        "where a string sits; ownership is a different fact, and turning nearness into "
        "ownership means choosing a distance, which is a threshold no published source "
        "supplies. On the twenty four published 2024 labels this project read there is "
        "no telephone number at all, so there is nothing to attribute, and each label "
        "carries one web address for the Energy Commission and one for the supplier, "
        "told apart by their domains, which PCL003 and PCL005 already decide without "
        "reading a single coordinate. Where a label sets a contact detail down with no "
        "owner beside it, the fact is missing from the document rather than from the "
        "tool, and a proximity rule that guessed wrong would attribute a contact detail "
        "to a named supplier. Reading a page down its columns was built for another "
        "reason after this was settled, and it does not reopen it: a cell tells you "
        "which column a string is in, not whose string it is.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL022",
        "Consistency with the annual resource report",
        "section 1393.1(a)(1)",
        "Information disclosed on each power content label shall be consistent with "
        "the information reported to the Energy Commission on the annual resource "
        "report for each electricity portfolio and for total power content.",
        "Requires the supplier's annual resource report as a second input. This tool "
        "reads one document at a time and does not fetch anything, and the report is "
        "not published alongside the label. The Energy Commission does publish a second "
        "file beside each label on the same page; four were read and each is an "
        "alternative rendering of the same label, not the report the consistency is "
        "measured against.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL023",
        "Total power content disclosure",
        "section 1393.1(c)",
        "Beginning January 1, 2026, each retail supplier shall also include the "
        "following information for its total power content.",
        "The trigger attaches to the supplier's act of disclosure, which subdivision "
        "(b)(2) dates to October 1 of each year, so what matters is when a label was "
        "disclosed. A label states its data year, not the date it was disclosed. "
        "Deriving one from the other means chaining subdivision (a) to subdivision "
        "(b)(2) and then deciding a supplier's obligation window on this tool's own "
        "reasoning. It becomes implementable if the project accepts that derivation "
        "and can calibrate it against a label from data year 2025 or later.",
        Blocker.CONDITIONAL,
    ),
    _registered_only(
        "PCL024",
        "Unspecified power annotation percentage",
        "section 1393.1(c)(7)",
        "Beginning in 2026, the annotation of unspecified power shall include the "
        "percentage of unspecified power provided by either 'Fossil Fuels' or "
        "'Renewables and Zero-Carbon Resources' as those groups are described in "
        "1393.1(c)(2), whichever group was greater for the previous year.",
        "The same trigger as PCL023, written as 'Beginning in 2026' rather than "
        "'Beginning January 1, 2026'. Blocked for the same reason and unblocked by the "
        "same thing.",
        Blocker.CONDITIONAL,
    ),
    _registered_only(
        "PCL025",
        "Fuel mix percentages against the displayed total",
        "section 1392(b)(1)",
        "The fuel mix for each electricity portfolio and for total power content shall "
        "be calculated by aggregating net purchases of each fuel type and expressed as "
        "percentages of the retail sales of the electricity portfolio or loss-adjusted "
        "load for total power content.",
        "The label displays whole percentages and the published text prescribes no "
        "rounding rule and no tolerance, so a column's components need not add to the "
        "total the label displays. On eight of the published 2024 labels this project "
        "read, fourteen of their thirty three columns had components summing to 99 or "
        "101 against a displayed total of 100. The statewide column the Energy "
        "Commission itself supplies under section 1393.1(a)(3) sums to 101 against a "
        "displayed 100 on all twenty four labels read, and no supplier computes it. An "
        "equality test would report a deviation for correctly rounded arithmetic, and "
        "any tolerance that suppressed it would be a threshold this tool invented "
        "rather than one a source supplies. Two further hazards sit behind that one: "
        "extracted text loses column boundaries on labels with several portfolios, and "
        "the RPS-eligible row is a subcategory of rows beneath it, so a naive sum "
        "double counts. PCL018 checks the total the label itself displays instead.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL026",
        "GHG emissions intensity value",
        "section 1392(b)",
        "Annual Accounting and the Power Content Label.",
        "Recomputing an emissions intensity needs the supplier's procurement data, the "
        "Energy Commission's assigned generator intensities, and loss factors. None of "
        "that is in the label. This tool checks the disclosure, not the number.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL027",
        "Disclosure timing",
        "section 1393.1(b)(2)",
        "The power content label shall be provided to the Energy Commission by "
        "October 1 of each year. The power content label shall also be displayed on the "
        "website of the retail supplier, if it maintains one for purposes of "
        "communicating information about electric service, in an easily marked and "
        "identifiable location by October 1 of each year.",
        "A publication date is a fact about when and where a document was posted, not "
        "a property of the document. A PDF creation timestamp is neither the date the "
        "label was provided nor the date it was posted, and it is trivially editable, "
        "so this tool does not read one. This tool is offline and checks files.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL028",
        "Custom electricity portfolios",
        "section 1393.1(e)",
        "Custom electricity portfolios negotiated under private agreement shall not be "
        "included in the power content labels provided to the retail supplier's general "
        "customers.",
        "Whether a portfolio was negotiated under private agreement is not discoverable "
        "from the label.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL029",
        "Retail sales and loss-adjusted load statement",
        "section 1393.1(c)(6)",
        "The label shall indicate that electricity portfolios represent retail sales, "
        "and that total power content and total California loss-adjusted load represent "
        "retail sales, other end uses, and losses.",
        "The regulation prescribes what the label must indicate but not the words it "
        "must use, unlike subdivision (l), whose footnote text is set out verbatim and "
        "which PCL013 to PCL015 match against. Any phrase matched here would be a rule "
        "this tool wrote, and a supplier who said the same thing differently would draw "
        "a false finding. It becomes checkable on the issued-format basis if the "
        "Energy Commission's own template carries a fixed rendering of the statement. "
        "Twenty four published 2024 labels, and four of the alternative renderings "
        "published beside them, were read for one. None carries any statement of it, "
        "so the template that would unblock this does not exist in the 2024 vintage.",
        Blocker.CONDITIONAL,
    ),
    _registered_only(
        "PCL030",
        "Emerging Technologies group",
        "section 1393.1(c)(2)(C)",
        "Emerging Technologies as identified in Section 1393.1(c)(1)(K). On a "
        "case-by-case basis, in accordance with other laws and regulations and based on "
        "information provided by impacted retail suppliers, Commission staff will "
        "evaluate the specific resource(s) within this category and, for purposes of "
        "the power content label, classify those resources as 'Emerging Technologies,' "
        "or, as appropriate based on the resource type, include those resources in the "
        "categories set forth in Section 1393.1(c)(2)(A) or 1393.1(c)(2)(B).",
        "Whether this group belongs on a given label depends on whether the supplier "
        "holds resources in category (K) and on a case-by-case classification Energy "
        "Commission staff make outside the document. PCL006 reports category (K) where "
        "it appears and never requires it, because subparagraph (K) is qualified 'if "
        "applicable'. Registered separately from PCL007 and PCL009 so that the third "
        "group in the same list is visible rather than silently skipped.",
        Blocker.PERMANENT,
    ),
    # -----------------------------------------------------------------------
    # Registered by the completeness sweep of 22 August 2026, which read
    # sections 1391 through 1394 end to end and diffed every obligation
    # against the catalog. Five requirements had been passed over in
    # silence, which is the failure docs/adr/0002 exists to prevent. The
    # sweep's method and its negative results are recorded in docs/sources.md.
    # -----------------------------------------------------------------------
    _registered_only(
        "PCL031",
        "Marketing claim consistency",
        "section 1393.1(a)(2)",
        "Any marketing or retail product claim by a retail supplier related to the GHG "
        "emissions intensity of an electricity portfolio shall be consistent with the GHG "
        "emissions intensity disclosed on the relevant power content label.",
        "Consistency runs between a marketing claim and the label, so deciding it needs "
        "the second document: the promotional material in which the claim was made. This "
        "tool reads the label it is handed and nothing else, and it will not go looking "
        "for a supplier's advertising. Whether some claim somewhere agrees with the "
        "disclosed figure is a fact about two documents together, and the label alone "
        "cannot exhibit a deviation from either side of the comparison.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL032",
        "Promotional materials inclusion",
        "section 1393.1(b)(1)",
        "The power content label shall be provided in all product-specific written "
        "promotional materials that are distributed to consumers by either printed or "
        "electronic means, including the retail supplier's Internet Web site, if one "
        "exists, except that advertisements and notices in general circulation media shall "
        "not be subject to this requirement.",
        "Whether the label reached consumers inside product-specific promotional "
        "materials is a fact about distribution, not about the document: a file cannot "
        "show where else it was sent or published. The placement rules inside those "
        "materials are PCL019 and the timing rules are PCL027; what subdivision (b)(1) "
        "adds is the duty to include the label at all, and no reading of the file itself "
        "can settle that it was included anywhere.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL033",
        "Single label for general customers",
        "section 1393.1(c)",
        "Each retail supplier shall disclose the following information for every "
        "electricity portfolio it offers, except for custom electricity portfolios, on a "
        "single power content label.",
        "That the general portfolios share one label turns on how many electricity "
        "portfolios the supplier offers, which the label does not say. A supplier with "
        "three portfolios might issue one conforming label covering all three, or three "
        "labels each conforming alone, and telling those cases apart from a custom "
        "portfolio arrangement under subdivision (e) needs the supplier's offering list, "
        "which is not part of any document this tool reads.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL034",
        "Grandfathered emissions exclusion identified",
        "section 1393.1(d)(2)",
        "Retail suppliers with specified purchases of eligible firmed-and-shaped products "
        "under a purchase agreement or ownership arrangement executed prior to January 1, "
        "2019 shall report GHG emissions associated with the delivered electricity and "
        "shall identify these emissions as excluded from the calculation of emissions "
        "intensities on the power content label.",
        "The duty to identify these emissions as excluded attaches only to suppliers "
        "whose purchase agreements predate January 1, 2019, and whether one does is not "
        "discoverable from the label. Presence would be visible and absence would not: "
        "one of the twenty four published labels read carries exclusion wording without "
        "any way to tell grandfathering from subdivision (d)(3) adjustments. A check "
        "built here could confirm and never deviate, adding to the implemented count "
        "without adding any ability to find anything, on the same asymmetry recorded "
        "against PCL020.",
        Blocker.PERMANENT,
    ),
    _registered_only(
        "PCL035",
        "Footnote secondary group percentage",
        "section 1393.1(l)(3)",
        "Unspecified power is electricity purchased from a genericized pool on the open "
        "market. [This footnote shall also provide the percentage of the secondary "
        "resource group, as specified under Section 1393.1(c)(2)(A)-(B), serving "
        "unspecified power in the previous year].",
        "The bracketed sentence appended to footnote 3 requires the percentage of the "
        "secondary resource group serving unspecified power. It travels with the 2026 "
        "annotation changes of subdivisions (c)(2) and (c)(7), blocked on the same "
        "unsettled question of whether the trigger attaches to disclosure date or data "
        "year, and unblocked by the same event: labels for data year 2025 or later "
        "showing how the Energy Commission renders the requirement. Becomes checkable "
        "when a published rendering supplies the words to match, on the ADR planned for "
        "the Track A trigger derivation.",
        Blocker.CONDITIONAL,
    ),
)

BY_ID: dict[str, RegisteredCheck] = {c.spec.id: c for c in CHECKS}


def implemented_checks() -> tuple[RegisteredCheck, ...]:
    return tuple(c for c in CHECKS if c.spec.implemented)


def unimplemented_checks() -> tuple[RegisteredCheck, ...]:
    return tuple(c for c in CHECKS if not c.spec.implemented)
