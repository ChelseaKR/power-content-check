"""The release workflow, read as code rather than trusted as configuration.

``release.yml`` triggers on ``workflow_dispatch`` only. No push, no pull
request. So nothing in CI has ever executed a line of it, and until it is
dispatched a step in it is unguarded code in a file the merge gate never runs.

That is not hypothetical here. The first ever dispatch, on 2026-09-07 for
``v0.1.0``, failed in the publish job with ``HTTP 500`` from the releases API.
The cause was a contradiction between the workflow's own two jobs:

* ``verify-tag`` **requires an annotated tag** -- ``git cat-file -t "${TAG}"``
  must print ``tag`` -- because a lightweight tag carries no signature to
  verify.
* ``publish`` then read ``/git/ref/tags/<tag>`` and passed ``.object.sha`` to
  ``gh release create --target``. On an annotated tag that field is the **tag
  object**, not the commit. ``--target`` wants a commitish.

So the publish job could never have succeeded for any tag the verify job would
accept, and the API's answer (``500``, not a ``422`` naming the field) said
nothing about which of the two SHAs was wanted. It passed ``03241d92`` where
``a258c77`` was needed.

The lesson is not "dereference the tag". It is that a ``workflow_dispatch``-only
file has no verdict of its own, ever, so anything load-bearing in it needs a
test that reads it. These assertions are that test.

Two things they deliberately do **not** do.

They do not substring-match for a job name or a step name. The word "verify"
appears in several places in that file for unrelated reasons, and a substring
test passes on a workflow whose ``needs:`` edge has actually been cut. The
dependency assertion walks the ``needs:`` closure instead.

They do not re-implement the workflow. They pin the three facts whose violation
is silent: that publishing depends on verification, that the signature check
demands an annotated tag, and that the SHA handed to ``--target`` is the one
that comes back from dereferencing a tag object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"

#: The API path that returns a *ref*. For an annotated tag its ``.object.sha``
#: is the tag object, which is not a commitish.
REF_ENDPOINT = "/git/ref/tags/"

#: The API path that dereferences a tag object. Its ``.object.sha`` is the
#: commit, which is what ``--target`` needs.
TAG_OBJECT_ENDPOINT = "/git/tags/"


def _workflow() -> dict[Any, Any]:
    """The parsed workflow.

    Keyed by ``Any`` rather than ``str`` on purpose: YAML 1.1 reads a bare
    ``on:`` as the boolean ``True``, so the trigger block is not under a string
    key at all. Declaring ``dict[str, Any]`` here typechecks and then fails at
    runtime on the one lookup that matters least obviously.
    """
    loaded = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), "release.yml did not parse as a mapping"
    return loaded


def _jobs() -> dict[str, Any]:
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict) and jobs, "release.yml declares no jobs"
    return jobs


def needs_closure(jobs: dict[str, Any], job: str) -> set[str]:
    """Every job that must succeed before ``job`` runs, transitively.

    Walked rather than read one level deep, so inserting a passthrough job
    between two of these does not quietly break the chain, and cutting an edge
    anywhere along it is visible here.
    """
    seen: set[str] = set()
    pending = [job]
    while pending:
        current = pending.pop()
        declared = jobs.get(current, {}).get("needs", [])
        parents = [declared] if isinstance(declared, str) else list(declared)
        for parent in parents:
            if parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return seen


def _run_scripts(job: dict[str, Any]) -> str:
    return "\n".join(
        str(step.get("run", "")) for step in job.get("steps", []) if isinstance(step, dict)
    )


def test_the_workflow_has_the_two_jobs_these_rules_are_about() -> None:
    """A rename would otherwise make every assertion below vacuous.

    Each of them looks a job up by name. If the name moved, ``.get`` would
    return an empty mapping and the checks would pass over nothing, which is
    the failure mode this whole module exists to prevent one level up.
    """
    assert {"verify-tag", "publish"} <= set(_jobs())


def test_publishing_depends_on_the_verification_job() -> None:
    """Walked transitively, because a substring test cannot see a cut edge."""
    assert "verify-tag" in needs_closure(_jobs(), "publish")


def test_the_needs_walk_notices_a_cut_edge() -> None:
    """Control on the walker, on synthetic input.

    Without it, ``needs_closure`` returning something wrong for every input
    would still satisfy the assertion above whenever the right name happened to
    appear -- and a walker that returned every job name would pass it always.
    """
    chain = {"a": {}, "b": {"needs": "a"}, "c": {"needs": ["b"]}}
    assert needs_closure(chain, "c") == {"a", "b"}
    assert needs_closure({"a": {}, "b": {}, "c": {"needs": ["b"]}}, "c") == {"b"}
    assert needs_closure({"a": {}, "c": {}}, "c") == set()


def test_the_signature_check_demands_an_annotated_tag() -> None:
    """A lightweight tag carries no signature, so verifying one proves nothing."""
    script = _run_scripts(_jobs()["verify-tag"])
    assert "cat-file -t" in script, (
        "verify-tag no longer checks the ref's object type, so a lightweight tag "
        "would reach `git verify-tag`, which cannot verify one"
    )


def test_the_published_target_is_dereferenced_from_the_tag_object() -> None:
    """The assertion that would have caught the HTTP 500.

    ``--target`` is given ``TAG_SHA``, and ``TAG_SHA`` has to be the commit. On
    an annotated tag -- the only kind ``verify-tag`` accepts -- that means the
    ref lookup has to be followed by a lookup of the tag object itself.
    """
    script = _run_scripts(_jobs()["publish"])
    assert REF_ENDPOINT in script, (
        "publish no longer re-resolves the tag through the API, so a tag moved "
        "after verify-tag ran would be published unverified"
    )
    assert TAG_OBJECT_ENDPOINT in script, (
        f"publish reads {REF_ENDPOINT} but never {TAG_OBJECT_ENDPOINT}, so the SHA "
        "it hands to `gh release create --target` is the annotated tag object "
        "rather than the commit. The releases API answers HTTP 500 to that, which "
        "names neither the field nor the two SHAs involved"
    )
    assert "TAG_SHA=${commit_sha}" in script, (
        "TAG_SHA is no longer assigned from the dereferenced commit, so whatever "
        f"{TAG_OBJECT_ENDPOINT} returns is being fetched and then discarded"
    )


def test_the_release_is_created_against_that_resolved_sha() -> None:
    """The other half: resolving a commit and then not using it would be silent."""
    script = _run_scripts(_jobs()["publish"])
    assert '--target "${TAG_SHA}"' in script


@pytest.mark.parametrize(
    ("trigger", "reachable"),
    [("workflow_dispatch", True), ("push", False), ("pull_request", False)],
)
def test_the_workflow_is_dispatch_only(trigger: str, reachable: bool) -> None:
    """Recorded, not enforced for its own sake.

    This is *why* the rules above exist rather than a rule about the trigger:
    a file CI never runs is a file whose only guard is a test that reads it. If
    a `push` trigger is ever added, these assertions stop being the sole guard
    and this parametrisation is the thing that says so.
    """
    workflow = _workflow()
    # YAML 1.1 reads a bare `on:` as the boolean True. Both spellings are
    # accepted so this does not become a rule about how the key is quoted.
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert (trigger in triggers) is reachable
