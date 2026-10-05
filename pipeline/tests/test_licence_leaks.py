"""No-derivatives and display-only values are shown only on server-rendered pages: the text that reaches the public
catalogue must not state them (registry rule for literature entries, validate rule for every catalogue entry)."""

from __future__ import annotations

import json

from envdash.models import CatalogEntry, Indicator, IndicatorFile, PublishedValueCitation
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


def _private(paths: Paths, indicator_id: str) -> tuple[Indicator, CatalogEntry]:
    raw = (paths.private_indicators / f"{indicator_id}.json").read_bytes()
    ind = IndicatorFile.model_validate_json(raw).to_indicator()
    catalog = json.loads((paths.data / "v1" / "catalog.json").read_text(encoding="utf-8"))
    entry = CatalogEntry.model_validate(next(e for e in catalog["indicators"] if e["id"] == indicator_id))
    return ind, entry


def test_the_catalogue_carries_no_quote_or_value_for_a_display_only_indicator() -> None:
    paths = Paths.default()
    ind, entry = _private(paths, "gmsl.ipcc-ar6.rise-2100-likely")
    assert entry.provenance.published_value is not None and entry.provenance.published_value.quote is None
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
