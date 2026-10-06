"""No-derivatives and display-only values are shown only on server-rendered pages: the text that reaches the public
catalogue must not state them (registry rule for literature entries, validate rule for every catalogue entry)."""

from __future__ import annotations

import json

import pytest

from envdash.models import CatalogEntry, IndicatorFile, PublishedValueCitation
from envdash.paths import Paths
from envdash.registry import _literature_leak_problem, load_registry
from envdash.validate import _private_values_in_catalogue

CARBON_BRIEF_SHARE = "carbon-brief-attribution-share-more-likely-or-severe"


def test_committed_literature_does_not_state_private_values() -> None:
    reg = load_registry(Paths.default())
    assert not [e for e in reg.literature_errors.values() if "states the value" in e]


def test_a_description_that_states_a_no_derivatives_value_is_refused() -> None:
    reg = load_registry(Paths.default())
    lit = reg.literature[CARBON_BRIEF_SHARE]
    assert _literature_leak_problem(reg, lit) is None
    leaky = lit.model_copy(update={"description": f"{lit.description} The share is {lit.value_text}."})
    problem = _literature_leak_problem(reg, leaky)
    assert problem is not None and "states the value" in problem


def _entry(paths: Paths, indicator_id: str) -> CatalogEntry:
    catalog = json.loads((paths.data / "v1" / "catalog.json").read_text(encoding="utf-8"))
    return CatalogEntry.model_validate(next(e for e in catalog["indicators"] if e["id"] == indicator_id))


def test_the_public_catalogue_has_no_quote_for_non_redistributable_values() -> None:
    catalog = json.loads((Paths.default().data / "v1" / "catalog.json").read_text(encoding="utf-8"))
    for raw in catalog["indicators"]:
        entry = CatalogEntry.model_validate(raw)
        pv = entry.provenance.published_value
        if entry.licence_class not in {"open", "share-alike", "noncommercial"} and pv is not None:
            assert pv.quote is None, entry.id


@pytest.mark.snapshot  # reads data-private/, which a local run has (or pulls from R2) and CI does not
def test_the_catalogue_does_not_state_a_display_only_value() -> None:
    paths = Paths.default()
    raw = (paths.private_indicators / "gmsl.ipcc-ar6.rise-2100-likely.json").read_bytes()
    ind = IndicatorFile.model_validate_json(raw).to_indicator()
    entry = _entry(paths, ind.id)
    assert _private_values_in_catalogue(ind, entry) == []
    value = next(o.value for o in ind.observations if o.value is not None)
    leaky = entry.model_copy(
        update={
            "provenance": entry.provenance.model_copy(
                update={
                    "published_value": PublishedValueCitation(document="x", locator="y", quote=None),
                    "description": f"{entry.provenance.description} The likely rise is {value} metres.",
                }
            )
        }
    )
    assert _private_values_in_catalogue(ind, leaky)
