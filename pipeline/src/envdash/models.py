"""The data contract: what a source is, what a snapshot records, and what a published indicator contains.

Every number on the site is an observation of an Indicator. An Indicator lists the Origins (exact raw files, by
sha256) it was computed from and the ProcessingSteps applied. Each Origin points at a Source, whose registry entry
(`pipeline/sources/<id>.yaml`) quotes the licence terms we rely on. The web types are generated from these models
(`pipeline/schema/openapi.json` -> `npm run gen:api`), so a change here is a change to the published files.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

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
        description="How the weekly run re-checks the quote: a machine-readable licence field (api: the JSON or XML "
        "response's text), the page's text, a PDF's text, or a person each quarter (bot-walled pages). api, page and "
        "pdf all match the quote against the normalised text of the body fetched from terms_url."
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
    key_header: str | None = Field(
        default=None,
        description="auth api-key: the request header that carries the key (e.g. x-api-key). Set this or key_query.",
    )
    key_query: str | None = Field(
        default=None,
        description="auth api-key: the query parameter that carries the key (e.g. client_id). Set this or key_header.",
    )
    cookie_accept_url: HttpUrl | None = Field(default=None, description="Licence click-through to visit first.")
    conditional: bool = Field(default=True, description="Server honours ETag/If-Modified-Since.")

    @model_validator(mode="after")
    def _consistent(self) -> Access:
        if (self.key_header or self.key_query) and self.auth != "api-key":
            raise ValueError("key_header and key_query apply only to auth api-key")
        if self.key_header and self.key_query:
            raise ValueError("set key_header or key_query, not both")
        return self


_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for m in names
}


def discover_key(m: re.Match[str]) -> str:
    """The comparable key of a link matched by a Discover pattern: the group `key` as written, or, for patterns with
    groups `year` and `month` instead, "YYYY-MM" (month as a number or an English month name or abbreviation)."""
    groups = m.groupdict()
    if groups.get("key") is not None:
        return groups["key"]
    month = groups["month"].lower()
    num = int(month) if month.isdigit() else _MONTHS.get(month)
    if num is None or not 1 <= num <= 12:
        raise ValueError(f"{groups['month']!r} is not a month")
    return f"{int(groups['year']):04d}-{num:02d}"


def _key_pattern(pattern: str, what: str) -> str:
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{what} {pattern!r} is not a valid regex: {e}") from None
    names = set(rx.groupindex)
    if "key" not in names and not {"year", "month"} <= names:
        raise ValueError(f"{what} {pattern!r} needs a named group 'key' (or groups 'year' and 'month')")
    return pattern


class Discover(Strict):
    """How to find the current file of an artifact whose file name changes on a schedule (a month or date in the
    name, a new upload folder each month). envdash/discover.py reads `listing_url` (an HTML page or directory
    listing), takes every link (href, resolved against the page URL, fragment dropped) and keeps those whose absolute
    URL matches `link_pattern` in full. The file taken is the one with the largest key. Keys are compared as text and
    must all have the same length (so fixed-width dates such as 202608 or 2026-08-31 order correctly); a tie between
    two different URLs, keys of different lengths, or no match at all is a failure, never a guess. The resolved URL
    is what is downloaded and what the snapshot manifest records as its url, with the listing(s) read in
    `discovery`.

    With `sublisting_pattern`, the links on `listing_url` that match it are listings themselves (monthly
    directories, monthly bulletin pages). They are read newest key first, and the first one with at least one
    `link_pattern` match supplies the file; at most `max_sublistings` are read before failing. This finds the newest
    file when the newest directory does not yet hold one (OISST final files lag the preliminary ones by two weeks)."""

    listing_url: HttpUrl = Field(description="The page or directory listing that links to the file.")
    link_pattern: str = Field(
        description="Regex matched in full against each link's absolute URL, with a named group 'key' (or 'year' and "
        "'month'). The file taken is the match with the largest key."
    )
    choose: Literal["max"] = Field(default="max", description="Which match to take: the largest key.")
    sublisting_pattern: str | None = Field(
        default=None,
        description="Regex, as link_pattern, for links on listing_url that are listings to search for link_pattern "
        "(newest key first). A link without a trailing slash is read as a directory (slash added) when the listing is "
        "a directory index.",
    )
    max_sublistings: int = Field(default=2, ge=1, le=12, description="How many sublistings to read before failing.")

    @model_validator(mode="after")
    def _patterns(self) -> Discover:
        _key_pattern(self.link_pattern, "link_pattern")
        if self.sublisting_pattern is not None:
            _key_pattern(self.sublisting_pattern, "sublisting_pattern")
        return self


ArtifactFormat = Literal["csv", "csv.gz", "txt", "tsv", "xlsx", "xls", "json", "xml", "zip", "nc", "pdf", "html", "rds"]


class Artifact(Strict):
    """One file (or API response) of a source."""

    id: Annotated[str, _match(SOURCE_ID, "artifact id")]
    url: HttpUrl | None = Field(
        description="Direct download URL; null for manual-only files and for files found through `discover`."
    )
    format: ArtifactFormat
    description: str
    access: Access = Access()
    max_bytes: int = Field(default=200_000_000, description="Refuse anything larger (protects R2 and runners).")
    discover: Discover | None = Field(
        default=None, description="Find the URL from a listing at each fetch, for files whose names change."
    )
    content_key: Literal["zip-members"] | None = Field(
        default=None,
        description="For files rebuilt on every request (a zip generated per download): zip-members fingerprints the "
        "sorted member names and the sha256 of each member's bytes, ignoring zip timestamps, order and compression. "
        "A fetch whose fingerprint equals the current snapshot's keeps that snapshot (no new vintage); the manifest "
        "records both the raw sha256 and this content_sha256.",
    )
    member_name_ignore: str | None = Field(
        default=None,
        description="content_key zip-members: a regex whose matches are removed from member names before "
        "fingerprinting, for producers that stamp the download date into every member name.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> Artifact:
        if self.url is not None and self.discover is not None:
            raise ValueError(f"artifact {self.id}: set url or discover, not both")
        if self.content_key == "zip-members" and self.format != "zip":
            raise ValueError(f"artifact {self.id}: content_key zip-members needs format zip")
        if self.member_name_ignore is not None:
            if self.content_key is None:
                raise ValueError(f"artifact {self.id}: member_name_ignore applies only with a content_key")
            try:
                re.compile(self.member_name_ignore)
            except re.error as e:
                raise ValueError(f"artifact {self.id}: member_name_ignore is not a valid regex: {e}") from None
        return self


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
        if self.acquisition == "automatic" and any(a.url is None and a.discover is None for a in self.artifacts):
            raise ValueError(f"{self.id}: automatic sources need a url (or discover) on every artifact")
        return self


# --- snapshots ----------------------------------------------------------------------------------------------------


class WaybackCapture(Strict):
    status: Literal["captured", "pending", "refused", "skipped"]
    url: HttpUrl | None = None
    captured_at: str | None = None
    reason: str | None = None


class SnapshotDiscovery(Strict):
    """How the url of a discovered artifact was found (see Discover)."""

    listing_url: HttpUrl = Field(description="The listing read first.")
    sublisting_url: HttpUrl | None = Field(default=None, description="The sublisting the file was found on, if any.")
    key: str = Field(description="The key of the link taken (the largest).")


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
    discovery: SnapshotDiscovery | None = Field(
        default=None, description="For artifacts with discover: the listing that url was resolved from."
    )
    content_key: Literal["zip-members"] | None = Field(
        default=None, description="The artifact's content_key when these bytes were recorded."
    )
    content_sha256: Sha256 | None = Field(
        default=None, description="Fingerprint of the content under content_key (sha256 stays the raw bytes')."
    )


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

TimeBasis = Literal["calendar", "years-before-1950"]
"""How an indicator's observations are placed in time.

calendar            `period` is an ISO 8601 year, year-month, date or range; `age_bp` is null.
years-before-1950   `age_bp` is the age as the producer publishes it, in years before 1950 (e.g. the gas age of air
                    in an ice core; negative after 1950); `period` is null. Ages are published as printed, never
                    rounded to calendar years (fractional ages would collide and pre-CE ages have no ISO year).
"""


def _time_problem(where: str, period: str | None, age_bp: float | None) -> str | None:
    """Exactly one of period and age_bp is set; an age must be a finite number."""
    if (period is None) == (age_bp is None):
        return f"{where}: set exactly one of period (calendar time) and age_bp (years before 1950)"
    if age_bp is not None and not math.isfinite(age_bp):
        return f"{where}: age_bp {age_bp!r} is not a finite number"
    return None


class Observation(Strict):
    entity: EntityCode
    period: Period | None = Field(
        default=None,
        description="ISO 8601 year, year-month, date or range. Null exactly when the indicator's time_basis is "
        "years-before-1950 (then age_bp is set).",
    )
    age_bp: float | None = Field(
        default=None,
        description="Age in years before 1950 as the producer publishes it (e.g. ice-core gas age; negative after "
        "1950). Set exactly when the indicator's time_basis is years-before-1950; otherwise null.",
    )
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

    @property
    def when(self) -> str:
        """The time label for messages: the period, or the age in years before 1950."""
        return self.period if self.period is not None else f"{self.age_bp!r} yr BP"

    @model_validator(mode="after")
    def _consistent(self) -> Observation:
        problem = _time_problem(f"{self.entity}", self.period, self.age_bp)
        if problem:
            raise ValueError(problem)
        if self.value is None and not self.missing_reason:
            raise ValueError(f"{self.entity} {self.when}: null value needs missing_reason")
        if (self.lower is None) != (self.upper is None):
            raise ValueError(f"{self.entity} {self.when}: lower and upper come together")
        if self.lower is not None and self.interval is None:
            raise ValueError(f"{self.entity} {self.when}: an uncertainty range needs its interval type")
        return self


class Latest(Strict):
    entity: EntityCode
    period: Period | None = Field(
        default=None, description="As Observation.period: null exactly when the time_basis is years-before-1950."
    )
    age_bp: float | None = Field(
        default=None,
        description="As Observation.age_bp: the youngest age, set exactly when the time_basis is years-before-1950.",
    )
    value: float
    status: Literal["final", "preliminary", "projection"]
    dims: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> Latest:
        problem = _time_problem(f"latest {self.entity}", self.period, self.age_bp)
        if problem:
            raise ValueError(problem)
        return self


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


class IndicatorBase(Strict):
    """What an indicator is, without its values: the fields Indicator and IndicatorFile share."""

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
    time_basis: TimeBasis = Field(
        default="calendar",
        description="calendar: every observation (and latest) has an ISO period and a null age_bp. "
        "years-before-1950: every observation (and latest) has age_bp and a null period; observations run from the "
        "oldest age to the youngest, and latest is the youngest.",
    )
    dimensions: list[Dimension] = Field(default_factory=list)
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
    def _meta_consistent(self) -> IndicatorBase:
        if self.licence_class == "excluded":
            raise ValueError(f"{self.id}: excluded sources are never published")
        if (self.kind == "published-value") != (self.published_value is not None):
            raise ValueError(f"{self.id}: published-value indicators (and only they) carry published_value")
        return self


class Indicator(IndicatorBase):
    """An indicator with its observations as records: the pipeline's in-memory form, and the shape the site works
    with after expanding a published IndicatorFile (web/src/lib/indicator-table.ts). Not itself a published file."""

    observations: list[Observation] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Indicator:
        paleo = self.time_basis == "years-before-1950"
        for when in [*self.observations, self.latest]:
            if paleo and when.period is not None:
                raise ValueError(f"{self.id}: time_basis years-before-1950 needs age_bp, not period {when.period!r}")
            if not paleo and when.period is None:
                raise ValueError(f"{self.id}: time_basis calendar needs a period, not age_bp {when.age_bp!r}")
        dim_ids = {d.id for d in self.dimensions}
        seen: set[tuple] = set()
        for o in self.observations:
            if set(o.dims) != dim_ids:
                raise ValueError(f"{self.id}: observation dims {sorted(o.dims)} != declared {sorted(dim_ids)}")
            key = (o.entity, o.period, o.age_bp, tuple(sorted(o.dims.items())))
            if key in seen:
                raise ValueError(f"{self.id}: duplicate observation {key}")
            seen.add(key)
        return self


# --- the published indicator file ---------------------------------------------------------------------------------

ObservationStatus = Literal["final", "preliminary", "projection"]

TABLE_OPTIONAL_COLUMNS: tuple[str, ...] = ("period", "age_bp", "lower", "upper", "interval", "missing_reason", "note")
"""Columns written only when they apply: period for calendar time, age_bp for years before 1950, the others only
when at least one row has a value. An absent column means null in every row; a column is never written as null."""


def _absent_not_null(schema: dict[str, Any]) -> None:
    # An optional column is left out, never written as null: its schema is the array alone, not required.
    for name in TABLE_OPTIONAL_COLUMNS:
        prop = schema["properties"][name]
        (array,) = [b for b in prop.pop("anyOf") if b.get("type") != "null"]
        prop.pop("default", None)
        prop.update(array)


class ObservationTable(BaseModel):
    """The observations of an indicator as columns: row i of the table is the i-th observation, in the order the
    pipeline produced them (the same order as the CSV's rows). Every column present has one entry per row."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=_absent_not_null)

    entity: list[EntityCode] = Field(min_length=1, description="Observation.entity of each row.")
    period: list[Period] | None = Field(
        default=None, description="Observation.period of each row. Present exactly when the time_basis is calendar."
    )
    age_bp: list[float] | None = Field(
        default=None,
        description="Observation.age_bp of each row. Present exactly when the time_basis is years-before-1950.",
    )
    value: list[float | None] = Field(description="Observation.value of each row; null where missing_reason says why.")
    lower: list[float | None] | None = Field(default=None, description="Observation.lower; absent when all null.")
    upper: list[float | None] | None = Field(default=None, description="Observation.upper; absent when all null.")
    interval: list[Interval | None] | None = Field(
        default=None, description="Observation.interval; absent when all null."
    )
    status: list[ObservationStatus] = Field(description="Observation.status of each row.")
    missing_reason: list[str | None] | None = Field(
        default=None, description="Observation.missing_reason; absent when all null."
    )
    note: list[Annotated[int, Field(ge=0)] | None] | None = Field(
        default=None,
        description="Index into the file's notes of each row's Observation.note, null for none; absent when no row "
        "has a note.",
    )
    dims: dict[str, list[str]] = Field(
        description="One column per declared dimension id: each row's dimension value id (Observation.dims)."
    )

    @model_serializer(mode="wrap")
    def _drop_absent(self, handler: SerializerFunctionWrapHandler):
        out = handler(self)
        return {k: v for k, v in out.items() if not (k in TABLE_OPTIONAL_COLUMNS and v is None)}


class IndicatorFile(IndicatorBase):
    """data/v1/indicators/<id>.json (and data-private/v1/indicators/<id>.json): an Indicator with its observations
    stored as columns. `table` holds one array per Observation field; notes are interned in `notes`, which lists each
    distinct note once (sorted by code point) and is indexed by table.note. Expanding row i of the table (absent
    columns read as null, table.note[i] read through notes) gives exactly Indicator.observations[i]."""

    table: ObservationTable
    notes: list[str] = Field(
        description="Every distinct Observation.note, each once, sorted by code point; table.note indexes into it."
    )

    @model_validator(mode="after")
    def _table_consistent(self) -> IndicatorFile:
        t = self.table
        rows = len(t.entity)
        columns: dict[str, list | None] = {
            "period": t.period,
            "age_bp": t.age_bp,
            "value": t.value,
            "lower": t.lower,
            "upper": t.upper,
            "interval": t.interval,
            "status": t.status,
            "missing_reason": t.missing_reason,
            "note": t.note,
            **{f"dims.{k}": v for k, v in t.dims.items()},
        }
        for name, col in columns.items():
            if col is not None and len(col) != rows:
                raise ValueError(f"{self.id}: table column {name} has {len(col)} rows, entity has {rows}")
        declared = {d.id for d in self.dimensions}
        if set(t.dims) != declared:
            raise ValueError(f"{self.id}: table dims {sorted(t.dims)} != declared {sorted(declared)}")
        paleo = self.time_basis == "years-before-1950"
        if paleo and (t.age_bp is None or t.period is not None):
            raise ValueError(f"{self.id}: time_basis years-before-1950 needs the age_bp column and no period column")
        if not paleo and (t.period is None or t.age_bp is not None):
            raise ValueError(f"{self.id}: time_basis calendar needs the period column and no age_bp column")
        for name in ("lower", "upper", "interval", "missing_reason", "note"):
            col = columns[name]
            if col is not None and all(v is None for v in col):
                raise ValueError(f"{self.id}: table column {name} is all null; it is written only when a row has one")
        if self.notes != sorted(set(self.notes)):
            raise ValueError(f"{self.id}: notes must be distinct and sorted")
        used = {i for i in t.note or [] if i is not None}
        if used != set(range(len(self.notes))):
            raise ValueError(f"{self.id}: table.note must use every entry of notes, and only those")
        return self

    @classmethod
    def from_indicator(cls, ind: Indicator) -> IndicatorFile:
        obs = ind.observations
        notes = sorted({o.note for o in obs if o.note is not None})
        index = {s: i for i, s in enumerate(notes)}

        def present(values: list) -> list | None:
            return values if any(v is not None for v in values) else None

        paleo = ind.time_basis == "years-before-1950"
        table = ObservationTable(
            entity=[o.entity for o in obs],
            period=None if paleo else [o.period for o in obs],
            age_bp=[o.age_bp for o in obs] if paleo else None,
            value=[o.value for o in obs],
            lower=present([o.lower for o in obs]),
            upper=present([o.upper for o in obs]),
            interval=present([o.interval for o in obs]),
            status=[o.status for o in obs],
            missing_reason=present([o.missing_reason for o in obs]),
            note=present([None if o.note is None else index[o.note] for o in obs]),
            dims={d.id: [o.dims[d.id] for o in obs] for d in ind.dimensions},
        )
        return cls(**{name: getattr(ind, name) for name in IndicatorBase.model_fields}, table=table, notes=notes)

    def to_indicator(self) -> Indicator:
        t = self.table
        rows = range(len(t.entity))

        def column(values: list | None) -> list:
            return values if values is not None else [None] * len(rows)

        period, age_bp, lower, upper = column(t.period), column(t.age_bp), column(t.lower), column(t.upper)
        interval, missing_reason, note = column(t.interval), column(t.missing_reason), column(t.note)
        observations = [
            Observation(
                entity=t.entity[i],
                period=period[i],
                age_bp=age_bp[i],
                value=t.value[i],
                lower=lower[i],
                upper=upper[i],
                interval=interval[i],
                status=t.status[i],
                missing_reason=missing_reason[i],
                note=None if note[i] is None else self.notes[note[i]],
                dims={k: v[i] for k, v in t.dims.items()},
            )
            for i in rows
        ]
        meta = {name: getattr(self, name) for name in IndicatorBase.model_fields}
        return Indicator(**meta, observations=observations)


# --- catalogue, status --------------------------------------------------------------------------------------------


class Provenance(Strict):
    """Everything about where an indicator came from, without its values. Public for every class: the files,
    fingerprints, steps and credits are metadata, so even a number we may not redistribute can be traced."""

    description: str
    kind: Literal["series", "published-value", "derived"]
    scope: Scope
    licence: Licence
    attribution: str
    notice: str | None = None
    origins: list[Origin] = Field(min_length=1)
    processing: list[ProcessingStep] = Field(min_length=1)
    published_value: PublishedValueRef | None = None


class CatalogEntry(Strict):
    """What the site needs to list and trace an indicator without loading it. Present for every class except
    excluded."""

    id: IndicatorId
    title: str
    unit: Unit
    display: Display
    licence_class: LicenceClass
    source_ids: list[SourceId]
    vintage: str
    time_basis: TimeBasis = Field(
        default="calendar", description="The indicator's time_basis: whether latest carries a period or an age_bp."
    )
    latest: Latest | None = Field(
        description="The headline value. Null for no-derivatives and display-only indicators: their values never "
        "appear under data/, so the site reads them from the private export on the server."
    )
    geo_coverage: Literal["global-only", "country", "mixed"]
    entities: list[EntityCode]
    downloadable: bool = Field(description="True only for redistributable classes.")
    export_sha256: Sha256 = Field(description="sha256 of the canonical indicator JSON (public or private).")
    provenance: Provenance

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
    """A value quoted from a paper, report or web page. The build checks that `quote` appears in the text of the
    snapshot of `source_id`/`artifact_id` and refuses to publish it otherwise: for a PDF artifact, the text of page
    `pdf_page`; for an html, json, xml or txt artifact (pdf_page null), the snapshot's whole normalised visible text
    (envdash.textmatch.snapshot_text)."""

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
    pdf_page: int | None = Field(
        default=None,
        ge=1,
        description="1-based page of the PDF file whose text must contain the quote. Required for a PDF artifact; "
        "null for html, json, xml and txt artifacts, whose whole visible text is searched.",
    )
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
