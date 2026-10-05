"""The data contract: what a source is, what a snapshot records, and what a published indicator contains.

Every number on the site is an observation of an Indicator. An Indicator lists the Origins (exact raw files, by
sha256) it was computed from and the ProcessingSteps applied. Each Origin points at a Source, whose registry entry
(`pipeline/sources/<id>.yaml`) quotes the licence terms we rely on. The web types are generated from these models
(`pipeline/schema/openapi.json` -> `npm run gen:api`), so a change here is a change to the published files.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl, model_validator

SCHEMA_VERSION = 1

# --- identifiers --------------------------------------------------------------------------------------------------

SOURCE_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# <quantity>.<source>.<variant>[.<more>], e.g. co2.noaa-gml.monthly-mlo
INDICATOR_ID = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+){1,3}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# ISO 8601 calendar periods we publish: year, year-month, date. Ranges use "/" (e.g. "2012/2021").
PERIOD = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?(/\d{4}(-\d{2}(-\d{2})?)?)?$")
# ISO 3166-1 alpha-3 for countries, or our aggregate codes from geo/entities.csv (WLD, EU27, ...).
ENTITY = re.compile(r"^[A-Z0-9_]{2,12}$")


def _match(pattern: re.Pattern[str], what: str):
    def check(v: str) -> str:
        if not pattern.fullmatch(v):
            raise ValueError(f"{what} {v!r} does not match {pattern.pattern}")
        return v

    return AfterValidator(check)


SourceId = Annotated[str, _match(SOURCE_ID, "source id")]
IndicatorId = Annotated[str, _match(INDICATOR_ID, "indicator id")]
Sha256 = Annotated[str, _match(SHA256, "sha256")]
Period = Annotated[str, _match(PERIOD, "period")]
EntityCode = Annotated[str, _match(ENTITY, "entity code")]


class Strict(BaseModel):
    # Exports always write every field (defaults included), so the published JSON schema marks them required and the
    # generated web types are not optional.
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_serialization_defaults_required=True)


# --- licences -----------------------------------------------------------------------------------------------------

LicenceClass = Literal["open", "share-alike", "noncommercial", "no-derivatives", "display-only", "excluded"]
"""What the producer's terms let the site do (see docs/licensing.md).

open            PD / CC0 / CC BY / OGL / attribution-only terms: chart, download, public raw mirror.
share-alike     CC BY-SA: as open, downloads carry CC BY-SA.
noncommercial   CC BY-NC(-SA) or custom non-commercial terms: chart and download carrying those terms.
no-derivatives  CC BY-NC-ND and similar: verbatim published values only (no shares, per-capita, rebasing), no download.
display-only    No licence, all rights reserved, or no re-hosting: shown with citation, no download, no mirror.
excluded        Never ingested.
"""

REDISTRIBUTABLE: frozenset[str] = frozenset({"open", "share-alike", "noncommercial"})
"""Classes whose derived values may be committed to data/, downloaded and archived on Zenodo."""

CLASS_ORDER: tuple[str, ...] = ("open", "share-alike", "noncommercial", "no-derivatives", "display-only", "excluded")


def strictest(classes: list[str]) -> str:
    """An output combining several sources carries the most restrictive class among them."""
    return max(classes, key=CLASS_ORDER.index)


class Licence(Strict):
    name: str = Field(description='Human name, e.g. "CC BY 4.0", "Public domain (US Government work)".')
    spdx: str | None = Field(description="SPDX id when one exists (CC-BY-4.0, OGL-UK-3.0, ...), else null.")
    url: HttpUrl | None = Field(description="The licence text or deed.")


class LicenceEvidence(Strict):
    """Why we believe the licence is what we say. A class without evidence is rejected by the validator."""

    terms_url: HttpUrl = Field(description="The producer's own page (or file) stating the terms.")
    licence_quote: str = Field(min_length=20, description="Verbatim text from terms_url that the class relies on.")
    checked_on: date
    terms_check: Literal["api", "page", "pdf", "manual"] = Field(
        description="How the weekly run re-checks the quote: a machine-readable licence field, the page's text, "
        "a PDF's text, or a person each quarter (bot-walled pages)."
    )


class Obligations(Strict):
    """What the terms require wherever the data appears. check-build verifies each one is rendered."""

    attribution: str = Field(description="Credit line. Placeholders: {version}, {date_accessed}, {year}.")
    attribution_modified: str | None = Field(
        default=None, description="Credit line used when we transformed the data (CC BY: indicate changes)."
    )
    notice: str | None = Field(default=None, description="Disclaimer or acknowledgement text that must appear.")
    derived_disclaimer: str | None = Field(default=None, description="Required text on adaptations (e.g. IEA).")
    rounding: str | None = Field(default=None, description="Rule the producer imposes on displayed values.")
    mirror_raw: bool = Field(description="Whether the unmodified raw file may be re-hosted publicly.")
    no_logo: bool = False
    no_endorsement: bool = False
    on_motif: str | None = Field(default=None, description="Credit wherever a derived motif appears site-wide.")


# --- sources ------------------------------------------------------------------------------------------------------


class Person(Strict):
    family: str | None = None
    given: str | None = None
    literal: str | None = Field(default=None, description="Institutional author.")


class Citation(Strict):
    """CSL-JSON subset, enough for APA and BibTeX."""

    type: Literal["dataset", "article-journal", "report", "webpage", "book", "chapter"]
    title: str
    author: list[Person]
    issued: str = Field(description="Year, or ISO date.")
    publisher: str | None = None
    container_title: str | None = Field(default=None, alias="container-title")
    volume: str | None = None
    page: str | None = None
    version: str | None = None
    DOI: str | None = None
    URL: HttpUrl | None = None
    text: str = Field(description="The producer's recommended citation, verbatim.")

    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, json_schema_serialization_defaults_required=True
    )


class Access(Strict):
    """How to reach a file. Anything a person must do by hand is acquisition=manual on the source."""

    method: Literal["GET"] = "GET"
    auth: Literal["none", "earthdata", "api-key", "cmems"] = "none"
    auth_env: str | None = Field(default=None, description="Env var holding the credential (from Keychain/secret).")
    cookie_accept_url: HttpUrl | None = Field(default=None, description="Licence click-through to visit first.")
    conditional: bool = Field(default=True, description="Server honours ETag/If-Modified-Since.")


class Artifact(Strict):
    """One file (or API response) of a source."""

    id: Annotated[str, _match(SOURCE_ID, "artifact id")]
    url: HttpUrl | None = Field(description="Direct download URL; null for manual-only files.")
    format: Literal["csv", "txt", "tsv", "xlsx", "json", "zip", "nc", "pdf", "html"]
    description: str
    access: Access = Access()
    max_bytes: int = Field(default=200_000_000, description="Refuse anything larger (protects R2 and runners).")


class SourceStatus(Strict):
    state: Literal["active", "at-risk", "archived", "discontinued"]
    note: str
    us_federal: bool = Field(description="Exposed to US federal programme cuts (2025-26).")


class NextRelease(Strict):
    expected: date
    note: str
    url: HttpUrl | None = None


class Source(Strict):
    id: SourceId
    title: str
    publisher: str
    landing_url: HttpUrl
    description: str
    citation: Citation
    licence_class: LicenceClass
    licence: Licence
    evidence: LicenceEvidence
    obligations: Obligations
    acquisition: Literal["automatic", "manual"]
    artifacts: list[Artifact] = Field(min_length=1)
    status: SourceStatus
    update_cadence: str
    next_release: NextRelease | None = None
    twins: list[SourceId] = Field(default_factory=list, description="Independent sources measuring the same thing.")
    research_ref: str = Field(description="Where the evidence lives, e.g. docs/research/sources-energy.json#Ember.")

    @model_validator(mode="after")
    def _consistent(self) -> Source:
        if self.licence_class in {"no-derivatives", "display-only", "excluded"} and self.obligations.mirror_raw:
            raise ValueError(f"{self.id}: class {self.licence_class} cannot have mirror_raw=true")
        if self.acquisition == "automatic" and any(a.url is None for a in self.artifacts):
            raise ValueError(f"{self.id}: automatic sources need a url on every artifact")
        return self


# --- snapshots ----------------------------------------------------------------------------------------------------


class WaybackCapture(Strict):
    status: Literal["captured", "pending", "refused", "skipped"]
    url: HttpUrl | None = None
    captured_at: str | None = None
    reason: str | None = None


class Snapshot(Strict):
    """The exact bytes we used, recorded once per sha256 (pipeline/manifests/snapshots/<sha256>.json)."""

    sha256: Sha256
    bytes: int = Field(ge=0)
    source_id: SourceId
    artifact_id: str
    url: HttpUrl | None = Field(description="Where the bytes came from; null if a person supplied the file.")
    date_accessed: date = Field(description="When these bytes were first fetched. Immutable for a sha256.")
    acquisition: Literal["automatic", "manual"]
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None
    r2_bucket: Literal["envdash-public", "envdash-private"] | None = None
    r2_key: str | None = None
    compression: Literal["zstd"] | None = "zstd"
    wayback: WaybackCapture | None = None
    note: str | None = Field(default=None, description="For manual files: who downloaded it from where.")


# --- indicators ---------------------------------------------------------------------------------------------------


class Unit(Strict):
    code: str = Field(description='Machine unit, e.g. "ppm", "degC", "GtCO2", "mm", "percent".')
    label: str = Field(description='Words, e.g. "parts per million".')
    short: str = Field(description='Compact, e.g. "ppm", "°C", "Gt CO₂".')


class Display(Strict):
    decimals: int = Field(ge=0, le=6)


class Scope(Strict):
    geography: str = Field(description='What the numbers cover, e.g. "Global mean", "Mauna Loa, Hawaii".')
    baseline: str | None = Field(default=None, description='e.g. "1850–1900 mean of this dataset".')
    gwp: Literal["AR5-GWP100", "AR6-GWP100", "GWP*"] | None = None
    lulucf: Literal["included", "excluded", "only"] | None = None
    bunkers: Literal["included", "excluded"] | None = None
    basis: str | None = Field(default=None, description='Any other scope note, e.g. "gross of cement carbonation".')


class DimensionValue(Strict):
    id: str
    label: str


class Dimension(Strict):
    id: str
    label: str
    values: list[DimensionValue]


Interval = Literal["1sigma", "2sigma", "90ci", "95ci", "likely", "very-likely", "range"]


class Observation(Strict):
    entity: EntityCode
    period: Period
    value: float | None
    lower: float | None = None
    upper: float | None = None
    interval: Interval | None = None
    status: Literal["final", "preliminary", "projection"] = "final"
    missing_reason: str | None = Field(default=None, description="Why value is null (producer sentinel, gap).")
    note: str | None = Field(
        default=None,
        description="What the producer's own file says about this value, in words (e.g. a month the producer "
        "interpolated, or measured at a substitute site). Never a judgement of ours.",
    )
    dims: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> Observation:
        if self.value is None and not self.missing_reason:
            raise ValueError(f"{self.entity} {self.period}: null value needs missing_reason")
        if (self.lower is None) != (self.upper is None):
            raise ValueError(f"{self.entity} {self.period}: lower and upper come together")
        if self.lower is not None and self.interval is None:
            raise ValueError(f"{self.entity} {self.period}: an uncertainty range needs its interval type")
        return self


class Latest(Strict):
    entity: EntityCode
    period: Period
    value: float
    status: Literal["final", "preliminary", "projection"]
    dims: dict[str, str] = Field(default_factory=dict)


class Origin(Strict):
    """One raw file an indicator was computed from (OWID origin fields, plus what makes it verifiable)."""

    source_id: SourceId
    artifact_id: str
    producer: str
    title: str
    version_producer: str | None = Field(description="The producer's own version label.")
    citation_full: str
    url_main: HttpUrl
    url_download: HttpUrl | None
    date_published: str | None = None
    date_accessed: date
    licence: Licence
    sha256: Sha256
    bytes: int
    etag: str | None = None
    last_modified: str | None = None
    wayback_url: HttpUrl | None = None
    r2_url: HttpUrl | None = Field(default=None, description="Public mirror; null when the licence forbids it.")
    doi: str | None = None
    acquisition: Literal["automatic", "manual"]


class ProcessingStep(Strict):
    script: str = Field(description="Repo path of the transform, e.g. pipeline/src/envdash/transforms/air/noaa_co2.py")
    transform_sha256: Sha256 = Field(description="sha256 of that file's source text.")
    lock_sha256: Sha256 = Field(description="sha256 of pipeline/uv.lock.")
    inputs: list[Sha256]
    description: str = Field(description="What was done, in words a reader can follow.")


class PublishedValueRef(Strict):
    """For values quoted from a paper or report rather than computed from a file."""

    document: str = Field(description="Source id of the paper/report.")
    locator: str = Field(description='e.g. "Table 3, p. 568" or "SPM statement C.10".')
    quote: str = Field(description="Verbatim text the value is taken from.")


class Indicator(Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    id: IndicatorId
    title: str
    description: str
    kind: Literal["series", "published-value", "derived"]
    unit: Unit
    display: Display
    scope: Scope
    geo_coverage: Literal["global-only", "country", "mixed"]
    headline_entity: EntityCode = Field(description="The entity whose latest value is the headline (usually WLD).")
    dimensions: list[Dimension] = Field(default_factory=list)
    observations: list[Observation] = Field(min_length=1)
    latest: Latest
    vintage: str = Field(description="Producer version or release label of the newest input.")
    origins: list[Origin] = Field(min_length=1)
    processing: list[ProcessingStep] = Field(min_length=1)
    licence_class: LicenceClass
    licence: Licence
    attribution: str = Field(description="Credit line as rendered (placeholders filled, modified variant if any).")
    notice: str | None = None
    published_value: PublishedValueRef | None = None
    superseded_by: IndicatorId | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Indicator:
        if self.licence_class == "excluded":
            raise ValueError(f"{self.id}: excluded sources are never published")
        if (self.kind == "published-value") != (self.published_value is not None):
            raise ValueError(f"{self.id}: published-value indicators (and only they) carry published_value")
        dim_ids = {d.id for d in self.dimensions}
        seen: set[tuple] = set()
        for o in self.observations:
            if set(o.dims) != dim_ids:
                raise ValueError(f"{self.id}: observation dims {sorted(o.dims)} != declared {sorted(dim_ids)}")
            key = (o.entity, o.period, tuple(sorted(o.dims.items())))
            if key in seen:
                raise ValueError(f"{self.id}: duplicate observation {key}")
            seen.add(key)
        return self


# --- catalogue, status --------------------------------------------------------------------------------------------


class CatalogEntry(Strict):
    """What the site needs to list an indicator without loading it. Present for every class except excluded."""

    id: IndicatorId
    title: str
    unit: Unit
    display: Display
    licence_class: LicenceClass
    source_ids: list[SourceId]
    vintage: str
    latest: Latest | None = Field(
        description="The headline value. Null for no-derivatives and display-only indicators: their values never "
        "appear under data/, so the site reads them from the private export on the server."
    )
    geo_coverage: Literal["global-only", "country", "mixed"]
    entities: list[EntityCode]
    downloadable: bool = Field(description="True only for redistributable classes.")
    export_sha256: Sha256 = Field(description="sha256 of the canonical indicator JSON (public or private).")

    @model_validator(mode="after")
    def _consistent(self) -> CatalogEntry:
        redistributable = self.licence_class in REDISTRIBUTABLE
        if self.downloadable != redistributable:
            raise ValueError(f"{self.id}: downloadable must be {redistributable} for class {self.licence_class}")
        if (self.latest is not None) != redistributable:
            raise ValueError(f"{self.id}: latest is published in the catalogue only for redistributable classes")
        return self


class Catalog(Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    indicators: list[CatalogEntry]


SourceState = Literal["ok", "unchanged", "failed", "manual"]


class SourceRunStatus(Strict):
    state: SourceState
    checked_at: str = Field(description="ISO datetime of this run's check.")
    reason: str | None = Field(default=None, description="Why it failed, in words.")
    last_success: str | None = None
    vintage: str | None = None
    manual_last_verified: date | None = None
    terms: Literal["unchanged", "changed", "unverifiable", "manual"] | None = None


class Status(Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    generated_at: str
    run_url: HttpUrl | None
    sources: dict[SourceId, SourceRunStatus]


class SourceList(Strict):
    """data/v1/sources.json: the public registry entries (pipeline/sources/*.yaml) as validated."""

    schema_version: Literal[1] = SCHEMA_VERSION
    sources: list[Source]


# --- literature (pipeline/literature/<id>.yaml) -------------------------------------------------------------------


class LiteratureObservation(Strict):
    entity: EntityCode
    period: Period
    value: float
    status: Literal["final", "preliminary", "projection"] = "final"


class LiteratureValue(Strict):
    """A value quoted from a paper or report. The build checks that `quote` appears in the text of the snapshot of
    `source_id`/`artifact_id` (on `pdf_page`) and refuses to publish it otherwise."""

    id: SourceId = Field(description="Equals the file name.")
    indicator_id: IndicatorId
    source_id: SourceId
    artifact_id: Annotated[str, _match(SOURCE_ID, "artifact id")]
    title: str
    description: str
    unit: Unit
    display: Display
    scope: Scope
    geo_coverage: Literal["global-only", "country", "mixed"]
    headline_entity: EntityCode
    vintage: str = Field(description='The edition of the document quoted, e.g. "AR6 WGIII (2022)".')
    locator: str = Field(description='Where in the document, as printed, e.g. "SPM statement C.12, p. 37".')
    pdf_page: int = Field(ge=1, description="1-based page of the PDF file whose text must contain the quote.")
    quote: str = Field(min_length=20, description="Verbatim text the value is taken from.")
    value_text: str = Field(description="The words inside `quote` that state the value.")
    value_reading: str = Field(description="How value_text becomes the number published, in words.")
    observations: list[LiteratureObservation] = Field(min_length=1)
    checked_on: date
    research_ref: str

    @model_validator(mode="after")
    def _consistent(self) -> LiteratureValue:
        if self.value_text not in self.quote:
            raise ValueError(f"{self.id}: value_text {self.value_text!r} is not part of the quote")
        return self
