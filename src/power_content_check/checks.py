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
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .citations import issued_format, reg
from .extract import LabelDocument
from .model import Basis, CheckResult, CheckSpec, Status

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
#: wording are accepted.
STATEWIDE_RENDERINGS = (
    "total california loss adjusted load",
    "california loss adjusted load",
    "total california system electricity",
    "california system electricity",
    "ca utility average",
    "california utility average",
)


@dataclass(frozen=True)
class CheckContext:
    """Facts a check needs that the document cannot supply on its own."""

    supplier_name: str | None = None


CheckFn = Callable[[LabelDocument, CheckContext], CheckResult]


def _ok(check_id: str, finding: str, detail: str | None = None) -> CheckResult:
    return CheckResult(check_id, Status.CONFORMS, finding, detail)


def _bad(check_id: str, finding: str, detail: str | None = None) -> CheckResult:
    return CheckResult(check_id, Status.DOES_NOT_CONFORM, finding, detail)


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
        "PCL001",
        f"The company name '{ctx.supplier_name}' does not appear in the label text.",
        "Section 1393.1(c)(4) lists the retail supplier's company name among the "
        "contents each label discloses.",
    )


def _pcl002(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    phones = _phones(doc)
    if len(phones) >= 2:
        return _ok("PCL002", f"{len(phones)} distinct telephone numbers appear on the label.")
    if len(phones) == 1:
        return _bad(
            "PCL002",
            "Only one telephone number appears on the label.",
            "Section 1393.1(c)(4) lists a telephone number for the retail supplier "
            "and a telephone number for the Energy Commission, which is two numbers.",
        )
    return _bad(
        "PCL002",
        "No telephone number appears in the label text.",
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
        "PCL003",
        "No web address for the retail supplier appears in the label text.",
        "Section 1393.1(c)(4) lists the retail supplier's website address among the "
        "contents each label discloses.",
    )


def _pcl004(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if "energy commission" in doc.normalized:
        return _ok("PCL004", "The label names the Energy Commission.")
    return _bad(
        "PCL004",
        "The words 'Energy Commission' do not appear in the label text.",
        "Section 1393.1(c)(4) lists the name of the Energy Commission among the "
        "contents each label discloses. A link to energy.ca.gov is checked "
        "separately by PCL005 and is not treated as the name.",
    )


def _pcl005(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if any("energy.ca.gov" in d for d in _domains(doc)):
        return _ok("PCL005", "The label carries an energy.ca.gov web address.")
    return _bad(
        "PCL005",
        "No Energy Commission web address appears in the label text.",
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
            "PCL006",
            f"{len(missing)} of the 10 unconditional fuel type categories are absent: "
            f"{', '.join(missing)}.",
            detail,
        )
    return _ok("PCL006", "All 10 unconditional fuel type categories appear on the label.", detail)


def _pcl007(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if "renewables and zero carbon resources" in doc.normalized:
        return _ok("PCL007", "The 'Renewables and Zero-Carbon Resources' group appears.")
    return _bad(
        "PCL007",
        "The 'Renewables and Zero-Carbon Resources' group does not appear in the label text.",
        "Section 1393.1(c)(2)(A) requires the fuel mix to be displayed in this group.",
    )


def _pcl008(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if re.search(r"rps\s+eligible\s+renewables", doc.normalized):
        return _ok("PCL008", "RPS-eligible renewables appear as a named subcategory.")
    return _bad(
        "PCL008",
        "RPS-eligible renewables do not appear as a named subcategory.",
        "Section 1393.1(c)(2)(A) provides that RPS-eligible renewables shall be "
        "identified as a subcategory of the Renewables and Zero-Carbon Resources group.",
    )


def _pcl009(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    if "fossil fuels" in doc.normalized:
        return _ok("PCL009", "The 'Fossil Fuels' group appears.")
    return _bad(
        "PCL009",
        "The 'Fossil Fuels' group does not appear in the label text.",
        "Section 1393.1(c)(2)(B) requires the fuel mix to be displayed in this group.",
    )


def _pcl010(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    text = doc.normalized
    if "greenhouse gas emissions intensity" not in text and "ghg emissions intensity" not in text:
        return _bad(
            "PCL010",
            "No greenhouse gas emissions intensity disclosure appears on the label.",
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
        "PCL011",
        "No disclosure of retired unbundled RECs appears on the label.",
        "Section 1393.1(c)(5) requires the quantity of unbundled RECs retired in "
        "association with each electricity portfolio, expressed as a percentage of "
        "retail sales. A mention of unbundled RECs in the footnote required by "
        "section 1393.1(l)(1) does not satisfy this.",
    )


def _pcl012(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    match = re.search(r"unspecified power\s*\(?\s*primarily\s+([a-z ]+?)\s*\)", doc.normalized)
    if match:
        group = match.group(1).strip()
        if group in GROUP_NAMES:
            return _ok(
                "PCL012",
                f"Unspecified power is annotated as primarily {group}.",
            )
        return _bad(
            "PCL012",
            f"Unspecified power is annotated as primarily '{group}', which is not one "
            "of the two resource groups.",
            "Section 1393.1(c)(7) requires the annotation to identify either "
            "'Fossil Fuels' or 'Renewables and Zero-Carbon Resources'.",
        )
    return _bad(
        "PCL012",
        "The display of unspecified power is not annotated with its predominant resource group.",
        "Section 1393.1(c)(7) requires the display of unspecified power to be "
        "annotated to identify whether it was provided primarily by 'Fossil Fuels' "
        "or 'Renewables and Zero-Carbon Resources'.",
    )


def _footnote_check(check_id: str, lead: str, ordinal: str) -> CheckFn:
    def run(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
        from .normalize import normalize

        if normalize(lead) in doc.normalized:
            return _ok(check_id, f"The footnote required by section 1393.1(l)({ordinal}) appears.")
        return _bad(
            check_id,
            f"The footnote required by section 1393.1(l)({ordinal}) does not appear.",
            f"The check matches the opening clause of the prescribed text: '{lead}'. "
            "It does not compare the whole footnote word for word.",
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


def _pcl016(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
    for rendering in STATEWIDE_RENDERINGS:
        if rendering in doc.normalized:
            return _ok(
                "PCL016",
                "The label separately discloses the statewide figures.",
                f"Matched the rendering '{rendering}'.",
            )
    return _bad(
        "PCL016",
        "The label does not separately disclose the statewide figures.",
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
        "PCL017",
        "The label does not identify the calendar year it covers.",
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
                "PCL018",
                f"A displayed column total is not 100 percent: {off}.",
                "Section 1392(b)(1) expresses the fuel mix as percentages of the "
                "portfolio's retail sales, and the labels the Energy Commission "
                "issues display a total row of 100 percent for every column.",
            )
        return _ok(
            "PCL018",
            f"All {len(values)} displayed column totals are 100 percent.",
        )
    return _unknown(
        "PCL018",
        "Not evaluated: no total row was located in the extracted text.",
        "Without a total row there is nothing to compare, and this tool does not "
        "recompute a supplier's fuel mix. See PCL025.",
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
        "issues, because a supplier may not alter that format.",
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
    # -----------------------------------------------------------------------
    _registered_only(
        "PCL019",
        "All label information in one place",
        "section 1393.1(h)",
        "All information contained in the power content label shall appear in one "
        "place without other intervening material.",
        "Deciding what counts as intervening material requires reading the document "
        "the label was published in, and judging layout. Extracted text does not "
        "support that judgment.",
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
        "the requirement was triggered, so it will not report either way.",
    ),
    _registered_only(
        "PCL021",
        "Attribution of contact details",
        "section 1393.1(c)(4)",
        "The retail supplier's company name, phone number, and website address, and "
        "the name, phone number, and website address of the Energy Commission.",
        "PCL002, PCL003 and PCL005 count contact details but cannot say which belongs "
        "to the supplier and which to the Energy Commission. Attribution depends on "
        "layout adjacency that extracted text does not preserve reliably.",
    ),
    _registered_only(
        "PCL022",
        "Consistency with the annual resource report",
        "section 1393.1(a)(1)",
        "Information disclosed on each power content label shall be consistent with "
        "the information reported to the Energy Commission on the annual resource "
        "report for each electricity portfolio and for total power content.",
        "Requires the supplier's annual resource report as a second input. This tool "
        "reads one document at a time and does not fetch anything.",
    ),
    _registered_only(
        "PCL023",
        "Total power content disclosure",
        "section 1393.1(c)",
        "Beginning January 1, 2026, each retail supplier shall also include the "
        "following information for its total power content.",
        "The trigger date is written against the calendar, and the source text does "
        "not settle whether it attaches to the label's publication date or to its data "
        "year. Enforcing it would mean choosing an interpretation the published text "
        "does not supply.",
    ),
    _registered_only(
        "PCL024",
        "Unspecified power annotation percentage",
        "section 1393.1(c)(7)",
        "Beginning in 2026, the annotation of unspecified power shall include the "
        "percentage of unspecified power provided by either 'Fossil Fuels' or "
        "'Renewables and Zero-Carbon Resources' as those groups are described in "
        "1393.1(c)(2), whichever group was greater for the previous year.",
        "Same unresolved trigger date as PCL023.",
    ),
    _registered_only(
        "PCL025",
        "Fuel mix percentages against the displayed total",
        "section 1392(b)(1)",
        "The fuel mix for each electricity portfolio and for total power content shall "
        "be calculated by aggregating net purchases of each fuel type and expressed as "
        "percentages of the retail sales of the electricity portfolio or loss-adjusted "
        "load for total power content.",
        "Summing a column means associating every figure on a row with the right "
        "portfolio. Extracted text loses column boundaries on labels with several "
        "portfolios, and a mis-associated column would produce a false arithmetic "
        "finding against a named supplier. PCL018 checks the total the label itself "
        "displays instead.",
    ),
    _registered_only(
        "PCL026",
        "GHG emissions intensity value",
        "section 1392(b)",
        "Annual Accounting and the Power Content Label.",
        "Recomputing an emissions intensity needs the supplier's procurement data, the "
        "Energy Commission's assigned generator intensities, and loss factors. None of "
        "that is in the label. This tool checks the disclosure, not the number.",
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
        "a property of the document. This tool is offline and checks files.",
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
    ),
)

BY_ID: dict[str, RegisteredCheck] = {c.spec.id: c for c in CHECKS}


def implemented_checks() -> tuple[RegisteredCheck, ...]:
    return tuple(c for c in CHECKS if c.spec.implemented)


def unimplemented_checks() -> tuple[RegisteredCheck, ...]:
    return tuple(c for c in CHECKS if not c.spec.implemented)
