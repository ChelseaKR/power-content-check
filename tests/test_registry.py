"""The catalog's own invariants.

Check identifiers are a public interface. Anyone who has filed a finding as
"PCL011" must be able to read that identifier the same way next year. The
pinned set below is the enforcement mechanism: adding a check means appending
to it, and retiring one means leaving the identifier in place and marking it
retired, never reassigning it.
"""

from __future__ import annotations

import re

import pytest

from power_content_check.checks import (
    CHECKS,
    CONDITIONAL_FUEL_TYPES,
    REQUIRED_FUEL_TYPES,
    implemented_checks,
    unimplemented_checks,
)
from power_content_check.model import Basis, Blocker, CheckSpec, Citation, Source

#: Frozen. Append only. Never renumber, never reuse.
EXPECTED_IDS = (
    "PCL001",
    "PCL002",
    "PCL003",
    "PCL004",
    "PCL005",
    "PCL006",
    "PCL007",
    "PCL008",
    "PCL009",
    "PCL010",
    "PCL011",
    "PCL012",
    "PCL013",
    "PCL014",
    "PCL015",
    "PCL016",
    "PCL017",
    "PCL018",
    "PCL019",
    "PCL020",
    "PCL021",
    "PCL022",
    "PCL023",
    "PCL024",
    "PCL025",
    "PCL026",
    "PCL027",
    "PCL028",
    "PCL029",
    "PCL030",
    "PCL031",
    "PCL032",
    "PCL033",
    "PCL034",
    "PCL035",
)

#: Frozen alongside the identifiers. A check may have its wording improved, but
#: an identifier that changes what it enforces is a renumbering in disguise.
EXPECTED_TITLES = {
    "PCL001": "Retail supplier company name",
    "PCL002": "Telephone numbers",
    "PCL003": "Retail supplier website address",
    "PCL004": "Energy Commission named",
    "PCL005": "Energy Commission website address",
    "PCL006": "Fuel type categories",
    "PCL007": "Renewables and Zero-Carbon Resources group",
    "PCL008": "RPS-eligible renewables subcategory",
    "PCL009": "Fossil Fuels group",
    "PCL010": "GHG emissions intensity units",
    "PCL011": "Retired unbundled RECs",
    "PCL012": "Unspecified power annotation",
    "PCL013": "Footnote: RPS compliance disclaimer",
    "PCL014": "Footnote: GHG exclusions",
    "PCL015": "Footnote: unspecified power definition",
    "PCL016": "Separate statewide disclosure",
    "PCL017": "Data year identified",
    "PCL018": "Displayed column totals",
    "PCL019": "All label information in one place",
    "PCL020": "Mixed portfolio footnote",
    "PCL021": "Attribution of contact details",
    "PCL022": "Consistency with the annual resource report",
    "PCL023": "Total power content disclosure",
    "PCL024": "Unspecified power annotation percentage",
    "PCL025": "Fuel mix percentages against the displayed total",
    "PCL026": "GHG emissions intensity value",
    "PCL027": "Disclosure timing",
    "PCL028": "Custom electricity portfolios",
    "PCL029": "Retail sales and loss-adjusted load statement",
    "PCL030": "Emerging Technologies group",
    "PCL031": "Marketing claim consistency",
    "PCL032": "Promotional materials inclusion",
    "PCL033": "Single label for general customers",
    "PCL034": "Grandfathered emissions exclusion identified",
    "PCL035": "Footnote secondary group percentage",
}

#: Pinned deliberately. A check here is one that no version of this tool,
#: reading the document it is handed, can decide. Moving an identifier out of
#: this set is a decision someone has to make on purpose, in a diff, with the
#: reason rewritten. That is the point: it stops the same question being
#: reopened every time somebody reads the catalog.
PERMANENTLY_UNIMPLEMENTABLE = {
    "PCL019",
    "PCL020",
    "PCL021",
    "PCL022",
    "PCL025",
    "PCL026",
    "PCL027",
    "PCL028",
    "PCL030",
    "PCL031",
    "PCL032",
    "PCL033",
    "PCL034",
}


def test_identifier_set_is_pinned() -> None:
    assert tuple(c.spec.id for c in CHECKS) == EXPECTED_IDS


def test_identifiers_are_unique() -> None:
    ids = [c.spec.id for c in CHECKS]
    assert len(ids) == len(set(ids))


def test_identifiers_follow_the_scheme() -> None:
    for check in CHECKS:
        assert re.fullmatch(r"PCL\d{3}", check.spec.id), check.spec.id


def test_titles_are_pinned() -> None:
    assert {c.spec.id: c.spec.title for c in CHECKS} == EXPECTED_TITLES


@pytest.mark.parametrize("check", CHECKS, ids=[c.spec.id for c in CHECKS])
def test_every_check_cites_a_fetched_source(check: object) -> None:
    spec = check.spec  # type: ignore[attr-defined]
    citation = spec.citation
    assert isinstance(citation, Citation)
    assert citation.locator.strip(), f"{spec.id} has no locator"
    assert citation.quote.strip(), f"{spec.id} has no quote"
    assert citation.source.url.startswith("https://"), f"{spec.id} cites a non-https source"
    assert citation.source.retrieved, f"{spec.id} cites a source with no retrieval date"


@pytest.mark.parametrize("check", CHECKS, ids=[c.spec.id for c in CHECKS])
def test_implemented_and_unimplemented_are_consistent(check: object) -> None:
    spec = check.spec  # type: ignore[attr-defined]
    run = check.run  # type: ignore[attr-defined]
    if spec.implemented:
        assert run is not None, f"{spec.id} claims to be implemented but has no callable"
        assert spec.unimplemented_reason is None
        assert spec.blocker is None
    else:
        assert run is None, f"{spec.id} is unimplemented but carries a callable"
        assert spec.unimplemented_reason, f"{spec.id} must say why it is not implemented"
        assert spec.blocker is not None, f"{spec.id} must say whether that is permanent"


def test_permanent_and_conditional_blockers_are_pinned() -> None:
    permanent = {c.spec.id for c in unimplemented_checks() if c.spec.blocker is Blocker.PERMANENT}
    assert permanent == PERMANENTLY_UNIMPLEMENTABLE


def test_a_conditional_blocker_names_what_would_unblock_it() -> None:
    """A reason that does not say what would change is a permanent one in disguise."""
    openers = ("becomes", "unblocked", "would settle it", "has not built", "does not exist")
    for check in unimplemented_checks():
        if check.spec.blocker is not Blocker.CONDITIONAL:
            continue
        reason = (check.spec.unimplemented_reason or "").lower()
        assert any(token in reason for token in openers), check.spec.id


def test_no_reason_is_a_placeholder() -> None:
    """'Not implemented yet' is not a reason. See docs/adr/0002."""
    for check in unimplemented_checks():
        reason = (check.spec.unimplemented_reason or "").strip()
        assert len(reason) > 80, check.spec.id
        assert "not implemented yet" not in reason.lower(), check.spec.id
        assert "todo" not in reason.lower(), check.spec.id


def test_template_basis_cites_the_issued_format() -> None:
    """A check that is not in the regulation's words must say so honestly."""
    for check in CHECKS:
        spec = check.spec
        if spec.basis is Basis.TEMPLATE_FORMAT:
            assert spec.citation.source.key == "cec-issued-labels-2024", spec.id


def test_the_split_between_implemented_and_registered_is_visible() -> None:
    assert len(implemented_checks()) + len(unimplemented_checks()) == len(CHECKS)
    assert len(implemented_checks()) == 18
    assert len(unimplemented_checks()) == 17


def test_fuel_type_lists_match_the_regulation() -> None:
    """Subparagraphs (A) through (L) of section 1393.1(c)(1), in order."""
    letters = [letter for letter, _ in REQUIRED_FUEL_TYPES + CONDITIONAL_FUEL_TYPES]
    assert letters == list("ABCDEFGHIJKL")
    assert len(REQUIRED_FUEL_TYPES) == 10
    assert len(CONDITIONAL_FUEL_TYPES) == 2


class TestSpecValidation:
    def _citation(self) -> Citation:
        source = Source(
            key="k",
            title="t",
            publisher="p",
            url="https://example.invalid/",
            retrieved="2026-08-17",
        )
        return Citation(source=source, locator="l", quote="q")

    def test_implemented_check_may_not_carry_a_reason(self) -> None:
        with pytest.raises(ValueError, match="unimplemented reason"):
            CheckSpec(
                id="PCL999",
                title="t",
                citation=self._citation(),
                basis=Basis.REGULATION_TEXT,
                implemented=True,
                what_it_looks_for="w",
                unimplemented_reason="because",
            )

    def test_unimplemented_check_must_carry_a_reason(self) -> None:
        with pytest.raises(ValueError, match="must say why"):
            CheckSpec(
                id="PCL999",
                title="t",
                citation=self._citation(),
                basis=Basis.REGULATION_TEXT,
                implemented=False,
                what_it_looks_for="w",
                blocker=Blocker.PERMANENT,
            )

    def test_unimplemented_check_must_classify_its_blocker(self) -> None:
        with pytest.raises(ValueError, match="whether that is permanent"):
            CheckSpec(
                id="PCL999",
                title="t",
                citation=self._citation(),
                basis=Basis.REGULATION_TEXT,
                implemented=False,
                what_it_looks_for="w",
                unimplemented_reason="because",
            )

    def test_implemented_check_may_not_carry_a_blocker(self) -> None:
        with pytest.raises(ValueError, match="carries a blocker"):
            CheckSpec(
                id="PCL999",
                title="t",
                citation=self._citation(),
                basis=Basis.REGULATION_TEXT,
                implemented=True,
                what_it_looks_for="w",
                blocker=Blocker.PERMANENT,
            )
