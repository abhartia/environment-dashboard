"""Climate Watch NDC Tracker: which Parties have submitted a 2025 nationally determined contribution (NDC 3.0), when,
and what Climate Watch codes the new NDC as containing.

Input: the Climate Watch API response for the 2025 NDC Tracker indicators (artifact ndc-tracker-2025, CC BY-NC 4.0
per Climate Watch's dataset metadata): {"categories", "sectors", "indicators"}, each indicator with its slug, name,
source, labels and `locations` (ISO 3166-1 alpha-3 code, or EUU for the European Union -> a list of
{"value": ...}). Every indicator used must have source "Climate Watch"; the query names only Climate Watch's own
2025 NDC Tracker fields, and the indicators of other organisations in the overview category are never read.

Published, one observation per Party and question, dated by the Party's 2025 NDC submission date (2025_date,
M/D/YYYY in the file, published as an ISO date):
- submitted: 2025_status. "Submitted 2025 NDC" and "Submitted 2025 NDC (Not Party to the Paris Agreement)" are 1,
  "Withdrawn 2025 NDC" is 0;
- the six content questions (2025_compare_1 to _6): Climate Watch's "Yes, ..." label is 1, its "No, ..." label 0.
  Labels that answer neither way ("No Document Submitted", "No revision compared with previous version", "No
  previous submission available") are published as null with the label as the reason.
Every value carries Climate Watch's label verbatim as its note (and, for `submitted`, the document title and link
from 2025_source), so nothing is lost in the 1/0 coding. Any label not listed below stops the transform.

Parties without a 2025_status entry are not published: Climate Watch has no information for them, which is not the
same as "not submitted". The EU's single NDC is coded for EUU (published as EU27) and repeated for each member state,
as in the file. The submission statement (2025_statement), a quotation from each NDC, is not used.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from envdash.geo import resolve
from envdash.models import Dimension, DimensionValue, Display, Observation, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "climate-watch-ndc"
TRACKER = Input(SOURCE, "ndc-tracker-2025")
INDICATOR = "ndc.climate-watch.2025-ndc"
PRODUCER = "Climate Watch"
ALIASES = {"EUU": "EU27"}

NO_ANSWER = ("No Document Submitted", "No revision compared with previous version", "No previous submission available")


@dataclass(frozen=True)
class Question:
    slug: str
    id: str
    label: str
    yes: tuple[str, ...]
    no: tuple[str, ...]


QUESTIONS: tuple[Question, ...] = (
    Question(
        "2025_status",
        "submitted",
        "Has submitted a 2025 NDC",
        ("Submitted 2025 NDC", "Submitted 2025 NDC (Not Party to the Paris Agreement)"),
        ("Withdrawn 2025 NDC",),
    ),
    Question(
        "2025_compare_1",
        "ghg-target-2035",
        "Includes a 2035 greenhouse gas target",
        ("Yes, 2035 GHG target included",),
        ("No, 2035 GHG target not included",),
    ),
    Question(
        "2025_compare_2",
        "economy-wide-target-2035",
        "Includes an economy-wide greenhouse gas target for 2035",
        ("Yes, economy-wide GHG target (for 2035) included",),
        ("No, no economy-wide GHG target (for 2035) included",),
    ),
    Question(
        "2025_compare_6",
        "non-co2-target",
        "Includes a quantified target for gases other than CO2",
        ("Yes, quantified non-CO2 target included",),
        ("No, no quantified non-CO2 target",),
    ),
    Question(
        "2025_compare_3",
        "strengthened-2030-target",
        "Strengthens the 2030 target",
        ("Yes, enhancement in the revised submission",),
        ("No, no enhancement in the revised submission",),
    ),
    Question(
        "2025_compare_4",
        "strengthened-adaptation",
        "Strengthens adaptation",
        ("Yes, enhancement in the revised submission",),
        ("No, no enhancement in the revised submission",),
    ),
    Question(
        "2025_compare_5",
        "added-clarity-transparency",
        "Adds information for clarity, transparency and understanding",
        ("Yes, enhancement in the revised submission",),
        ("No, no enhancement in the revised submission",),
    ),
)
DATE_SLUG, SOURCE_SLUG = "2025_date", "2025_source"
LINK = re.compile(r'<a href="(?P<url>https?://[^"]+)">(?P<title>[^<]+)</a>')
MDY = re.compile(r"(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4})")

UNIT = Unit(code="yes-no", label="1 = yes, 0 = no, as coded by Climate Watch", short="")


class ClimateWatchFormatError(ValueError):
    pass


def _single(ind: dict, iso: str) -> str:
    entries = ind["locations"][iso]
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0].get("value"), str):
        raise ClimateWatchFormatError(f"{ind['slug']} {iso}: expected one text value, got {entries!r}")
    return entries[0]["value"]


def read_indicators(raw: bytes) -> dict[str, dict]:
    doc = json.loads(raw)
    if not isinstance(doc, dict) or "indicators" not in doc:
        raise ClimateWatchFormatError("expected an object with 'indicators'")
    by_slug: dict[str, dict] = {}
    for ind in doc["indicators"]:
        if ind.get("source") != PRODUCER:
            raise ClimateWatchFormatError(f"indicator {ind.get('slug')!r} has source {ind.get('source')!r}")
        if ind["slug"] in by_slug:
            raise ClimateWatchFormatError(f"indicator {ind['slug']!r} appears twice")
        by_slug[ind["slug"]] = ind
    missing = [s for s in (*(q.slug for q in QUESTIONS), DATE_SLUG, SOURCE_SLUG) if s not in by_slug]
    if missing:
        raise ClimateWatchFormatError(f"indicators missing from the response: {missing}")
    return by_slug


def submission_date(text: str, iso: str) -> str:
    m = MDY.fullmatch(text)
    if m is None:
        raise ClimateWatchFormatError(f"{iso}: 2025_date {text!r} is not M/D/YYYY")
    return date(int(m["y"]), int(m["m"]), int(m["d"])).isoformat()


def entity(iso: str) -> str:
    return resolve(ALIASES.get(iso, iso), "iso3")


def observations(by_slug: dict[str, dict]) -> list[Observation]:
    parties = sorted(by_slug["2025_status"]["locations"])
    dates = {iso: submission_date(_single(by_slug[DATE_SLUG], iso), iso) for iso in parties}
    obs: list[Observation] = []
    for q in QUESTIONS:
        ind = by_slug[q.slug]
        outside = sorted(set(ind["locations"]) - set(parties))
        if outside:
            raise ClimateWatchFormatError(f"{q.slug} codes Parties without a 2025_status: {outside}")
        for iso in sorted(ind["locations"]):
            label = _single(ind, iso)
            note = f"Climate Watch: {label}."
            if q.slug == "2025_status" and iso in by_slug[SOURCE_SLUG]["locations"]:
                m = LINK.fullmatch(_single(by_slug[SOURCE_SLUG], iso))
                if m is None:
                    raise ClimateWatchFormatError(f"{iso}: 2025_source is not one link")
                note += f" Document: {m['title']} ({m['url']})."
            common = {"entity": entity(iso), "period": dates[iso], "note": note, "dims": {"question": q.id}}
            if label in q.yes:
                obs.append(Observation(value=1.0, **common))
            elif label in q.no:
                obs.append(Observation(value=0.0, **common))
            elif label in NO_ANSWER:
                obs.append(Observation(value=None, missing_reason=f"Climate Watch codes this as '{label}'.", **common))
            else:
                raise ClimateWatchFormatError(f"{q.slug} {iso}: label {label!r} is not one this transform reads")
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[TRACKER.key]
    by_slug = read_indicators(f.path.read_bytes())
    obs = observations(by_slug)
    accessed = f.snapshot.date_accessed.isoformat()
    latest = max(o.period for o in obs if o.period)
    n_parties = len(by_slug["2025_status"]["locations"])
    return Result(
        observations=obs,
        vintage=f"NDC Tracker retrieved {accessed} (latest 2025 NDC dated {latest})",
        date_published=None,
        steps=[
            f"Read the Climate Watch API response (sha256 {f.snapshot.sha256[:12]}…, retrieved {accessed}) and checked "
            "that every indicator in it has source 'Climate Watch'.",
            f"For the {n_parties} locations with a 2025 NDC status, coded the submission status and the six content "
            "questions as 1 (Climate Watch's 'Yes' or 'Submitted' label) or 0 ('No' or 'Withdrawn'); labels that "
            "answer neither way are published as missing, with the label. Each value keeps Climate Watch's label "
            "as its note.",
            "Dated each observation by the Party's 2025 NDC date (M/D/YYYY in the file, written as an ISO date). EUU "
            "(the European Union) is published as EU27.",
        ],
        changes="Climate Watch's yes/no labels coded as 1 and 0, with the labels kept as notes.",
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="2025 climate pledges (NDCs): who has submitted, and what they contain",
                description="Whether each country has submitted its 2025 nationally determined contribution "
                "(NDC 3.0, the national climate plan due under the Paris Agreement), when, and what Climate Watch "
                "finds in it: a 2035 greenhouse gas target, an economy-wide target, a target for gases other than "
                "carbon dioxide, a stronger 2030 target, stronger adaptation, and added information for clarity. "
                "1 means yes and 0 means no, as coded by the World Resources Institute's Climate Watch from the NDC "
                "texts. Countries Climate Watch has no information for are not shown.",
                kind="derived",
                unit=UNIT,
                display=Display(decimals=0),
                scope=Scope(
                    geography="Parties to the UNFCCC with a 2025 NDC status in Climate Watch; the EU's NDC is "
                    "coded for the EU and for each member state",
                    basis="Qualitative coding by Climate Watch (World Resources Institute) from the NDC documents on "
                    "the UNFCCC registry. Each observation is dated by the NDC's submission date.",
                ),
                geo_coverage="mixed",
                headline_entity="EU27",
                dimensions=(
                    Dimension(
                        id="question",
                        label="Question",
                        values=[DimensionValue(id=q.id, label=q.label) for q in QUESTIONS],
                    ),
                ),
                headline_dims=(("question", "submitted"),),
            ),
            inputs=(TRACKER,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=100, value_range=(0.0, 1.0)),
        )
    ]
