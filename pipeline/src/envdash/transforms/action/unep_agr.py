"""UNEP Adaptation Gap Report 2025 ("Running on empty"): what adapting to climate change will cost developing
countries each year by 2035, the international public finance for adaptation that developed countries commit to
them (2019-2023), and how many times the first is the second, as printed in the report.

Inputs: the report PDF (unep-agr-2025/report-pdf) and, for the flows, its online annexes PDF
(unep-agr-2025/online-annexes-pdf). UNEP's repository refuses scripted requests, so a person downloads both files
and records them with envdash snapshot add; the snapshot manifests' notes say who, when and from where.

Which pages. The PDF pages are fixed (the 4 November 2025 revision, 98 pages; the annexes, 60 pages): there is no
search for the text and no second page to try. Each value is read from the page named in its Statement, and the
build stops if that text is not on that page, so a replaced file whose pages moved fails until PAGES are checked.

How each value is checked before it is published (every check must pass, or nothing is published):
- Statement: a sentence of the report and the value phrase inside it ("US$310 billion/year"). The sentence must be
  in the text of its page (textmatch, which ignores whitespace and dashes), and the value phrase must also appear
  there with its spacing, dashes and digit boundaries as printed (so "12–14 times" cannot be read from "112–14" and
  "US$365 billion" cannot be read from "US$310–365 billion"). The number published is the value phrase's digits.
- Figure 4.4 (PDF p. 65, printed 47) prints its data labels as text. For each year 2019-2023 the page's text has
  five consecutive lines: the adaptation, mitigation and cross-cutting commitments, their total, and the year, in
  the order of the figure's legend ("Adaptation Mitigation Cross-cutting"). The transform requires the figure's title,
  axis label and legend on the page and each declared block (FIGURE_44) as five whole lines; it checks that each
  total is the sum of its three parts within the rounding of one-decimal labels (0.15), and that the 2023 adaptation
  label equals the 25.9 the same page states in words ("declined slightly in 2023 to US$25.9 billion"). Only the
  adaptation labels are published; nothing is measured from the bars.
- The Foreword (PDF p. 9) rounds the flows: "fell from US$28 billion in 2022 to US$26 billion in 2023". Its sentence
  is checked on the page and both numbers are publisher cross-checks of the flow series (half a unit: 27.9 and 25.9
  pass).
- Where the flows come from: the report says the flows analysis is "based on data from the Organisation for Economic
  Co-operation and Development (OECD)" (PDF p. 64), and online annex 4.B (annexes PDF p. 48, printed 45) names the
  OECD DAC Climate-Related Development Finance (CRDF) data set (recipients' perspective), commitments at 2023
  constant prices. Both sentences are checked and stated in the flows' processing steps.

What is not published: the report's 'gap' (needs minus flows) and any value we would compute; the LDC and SIDS rows
of Table 4.2; the inflation-adjusted range; the Glasgow doubling goal. The two lines of evidence are the ends of the
report's range ("This is based on two lines of evidence"), so the range is published as those two values, never as a
midpoint.

Licence class noncommercial (UNEP's notice: reproduction for educational or non-profit services with
acknowledgement, no commercial use; owner decision of 2026-10-08 for every UNEP report).
"""

from __future__ import annotations

import functools
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import (
    Input,
    InputFile,
    OriginMeta,
    PublisherCheck,
    Result,
    Spec,
    Transform,
    Validation,
)

SOURCE = "unep-agr-2025"
REPORT = Input(SOURCE, "report-pdf")
ANNEXES = Input(SOURCE, "online-annexes-pdf")
VINTAGE = "Adaptation Gap Report 2025: Running on empty"
REPORT_URL = "https://wedocs.unep.org/bitstream/handle/20.500.11822/48798/AGR2025.pdf"
ANNEXES_PAGE = "https://wedocs.unep.org/handle/20.500.11822/48839"
ENTITY = "UNEP_AGR_DEV"
REPORT_PAGES = 98
ANNEX_PAGES = 60


class AgrTextError(ValueError):
    pass


@dataclass(frozen=True)
class Statement:
    page: int
    """1-based PDF page of the file whose text holds the sentence."""
    printed_page: str
    sentence: str
    """Words of the report, as printed (whitespace and line breaks aside)."""
    value: str
    """The value phrase inside `sentence`, with its spacing and dashes as printed."""

    @property
    def locator(self) -> str:
        return f"p. {self.printed_page}"


# --- the statements ------------------------------------------------------------------------------------------------

RANGE_KEY_MESSAGE = Statement(
    58,
    "40",
    "the costs of adaptation are estimated to be in a plausible central range of US$310–365 billion/year for "
    "developing countries by the year 2035 (in constant 2023 prices, not inflation-adjusted). This is based on two "
    "lines of evidence",
    "US$310–365 billion/year",
)
RANGE_SUMMARY = Statement(
    13,
    "xiii",
    "The reanalysis estimates the costs of adaptation to be in a plausible central range of US$310–365 billion per "
    "year for developing countries by the year 2035 (in 2023 prices).",
    "US$310–365 billion per year",
)
MODELLED_COSTS = Statement(
    58,
    "40",
    "An updated modelling analysis estimates adaptation costs at US$310 billion/year for developing countries by 2035.",
    "US$310 billion/year",
)
FINANCE_NEEDS = Statement(
    58,
    "40",
    "An updated assessment of submitted national adaptation plans (NAPs) and nationally determined contributions "
    "(NDCs), with extrapolation to all developing countries, estimates adaptation finance needs at US$365 "
    "billion/year for the period 2023–2035.",
    "US$365 billion/year",
)
FLOWS_2023_SUMMARY = Statement(
    13,
    "xiii",
    "the latest available international public adaptation finance flows from developed country Parties to developing "
    "country Parties were tracked at US$26 billion in 2023 (constant 2023 prices).",
    "US$26 billion in 2023",
)
FLOWS_2023_KEY_MESSAGE = Statement(
    58,
    "40",
    "International public adaptation finance flows to developing countries were tracked at US$26 billion in 2023 (in "
    "constant 2023 prices), a slight decline compared to 2022.",
    "US$26 billion in 2023",
)
FLOWS_FOREWORD = Statement(
    9,
    "ix",
    "international public adaptation finance flows from developed to developing countries fell from US$28 billion in "
    "2022 to US$26 billion in 2023.",
    "US$28 billion in 2022 to US$26 billion in 2023",
)
FLOWS_2023_TEXT = Statement(
    65,
    "47",
    "Considering only developed to developing countries' flows, international public adaptation finance declined "
    "slightly in 2023 to US$25.9 billion (constant 2023 prices) compared to 2022 levels (figure 4.4).",
    "US$25.9 billion",
)
RATIO_KEY_MESSAGE = Statement(
    58,
    "40",
    "The estimated future costs/needs are approximately 12–14 times as much as international public flows.",
    "12–14 times",
)
RATIO_WITH_PRIVATE = Statement(
    68,
    "50",
    "Note that the gap would fall to 10–12 times as much if mobilized private adaptation sector flows from "
    "international public finance were included.",
    "10–12 times",
)
RATIO_SUMMARY = Statement(
    13,
    "xiii",
    "with needs that are 12–14 times as much as current finance flows",
    "12–14 times",
)
OECD_IN_REPORT = Statement(
    64,
    "46",
    "covering the most recent five-year available period (2019–2023), based on data from the Organisation for "
    "Economic Co-operation and Development (OECD). For further details, see annex 4.B.",
    "2019–2023",
)
OECD_IN_ANNEX = Statement(
    48,
    "45",
    "Data on adaptation finance flows have been obtained from the Organisation for Economic Co-operation and "
    "Development (OECD) Development Assistance Committee (DAC)'s Climate-Related Development Finance (CRDF) data set "
    "(recipients' perspective).",
    "Climate-Related Development Finance (CRDF) data set",
)
COMMITMENTS_IN_ANNEX = Statement(48, "45", "All values are commitments at 2023 constant prices.", "2023")

FIGURE_44_PAGE = 65
FIGURE_44_TEXTS = (
    "Figure 4.4 International public climate finance commitments from developed countries towards developing "
    "countries per year for the period 2019–2023, disaggregated into adaptation, mitigation and cross-cutting finance "
    "(US$ billions, constant 2023 prices)",
    "US$ billion (2023 constant prices)",
    "Adaptation Mitigation Cross-cutting",
    "Note: These values do not include the private flows mobilized from international public finance or export credits",
)


@dataclass(frozen=True)
class FigureYear:
    year: str
    adaptation: str
    mitigation: str
    cross_cutting: str
    total: str

    @property
    def lines(self) -> list[str]:
        return [self.adaptation, self.mitigation, self.cross_cutting, self.total, self.year]


# Figure 4.4's data labels, as printed (US$ billion, constant 2023 prices), each year's block in page-text order.
FIGURE_44: tuple[FigureYear, ...] = (
    FigureYear("2019", "19.8", "34.7", "6.9", "61.3"),
    FigureYear("2020", "24.7", "36.2", "8.0", "68.9"),
    FigureYear("2021", "21.3", "35.8", "7.3", "64.4"),
    FigureYear("2022", "27.9", "51.8", "13.2", "92.9"),
    FigureYear("2023", "25.9", "58.1", "14.8", "98.8"),
)


# --- reading and checking ------------------------------------------------------------------------------------------


class PdfPages:
    """The text of a PDF's pages (pypdf, as textmatch.pdf_pages_text), extracted when first asked for, so only the
    pages read are extracted. Indexed from 0, like a list of page texts."""

    def __init__(self, path: Path, expected_pages: int) -> None:
        from pypdf import PdfReader

        logging.getLogger("pypdf").setLevel(logging.ERROR)
        self._reader = PdfReader(path)
        if len(self._reader.pages) != expected_pages:
            raise AgrTextError(
                f"the PDF has {len(self._reader.pages)} pages, not {expected_pages}: UNEP has replaced the file, so "
                "every page number in unep_agr.py must be checked against it"
            )
        self._text: dict[int, str] = {}

    def __len__(self) -> int:
        return len(self._reader.pages)

    def __getitem__(self, index: int) -> str:
        if index not in self._text:
            self._text[index] = self._reader.pages[index].extract_text() or ""
        return self._text[index]


@functools.lru_cache(maxsize=4)
def pages_text(path: Path, expected_pages: int) -> PdfPages:
    """The pages of a snapshot. Cached by the content-addressed snapshot path."""
    return PdfPages(path, expected_pages)


_DASH = "[-‐‑‒–—―−]"


def _phrase_pattern(printed: str) -> re.Pattern[str]:
    """`printed` as a regex: runs of whitespace match any whitespace, any dash matches any dash, and a number at either
    end may not continue into another digit (or a decimal point before it)."""
    parts = []
    for token in re.split(r"(\s+|[-‐‑‒–—―−])", printed):
        if not token:
            continue
        if token.isspace():
            parts.append(r"\s+")
        elif re.fullmatch(_DASH, token):
            parts.append(rf"\s*{_DASH}\s*")
        else:
            parts.append(re.escape(token))
    body = "".join(parts)
    if printed[:1].isdigit():
        body = r"(?<![\d.])" + body
    if printed[-1:].isdigit():
        body = body + r"(?![\d])"
    return re.compile(body)


def phrase_on_page(page: str, printed: str) -> bool:
    return _phrase_pattern(printed).search(page) is not None


def verify(pages: Sequence[str] | PdfPages, s: Statement) -> None:
    if s.value not in s.sentence:
        raise AgrTextError(f"value phrase {s.value!r} is not part of its sentence {s.sentence[:60]!r}")
    page = pages[s.page - 1]
    if not textmatch.contains(page, s.sentence):
        raise AgrTextError(f"sentence not found on PDF page {s.page}: {s.sentence[:80]!r}...")
    if not phrase_on_page(page, s.value):
        raise AgrTextError(f"{s.value!r} is not printed as such on PDF page {s.page}")


def number(printed: str) -> Decimal:
    """The single number in a value phrase ("US$310 billion/year" -> 310)."""
    found = re.findall(r"\d+(?:\.\d+)?", printed)
    if len(found) != 1:
        raise AgrTextError(f"{printed!r} does not state exactly one number")
    return Decimal(found[0])


def range_ends(printed: str) -> tuple[Decimal, Decimal]:
    """The two ends of a printed range ("US$310–365 billion/year" -> 310, 365)."""
    m = re.search(rf"(\d+(?:\.\d+)?)\s*{_DASH}\s*(\d+(?:\.\d+)?)", printed)
    if m is None:
        raise AgrTextError(f"{printed!r} is not a range")
    lo, hi = Decimal(m.group(1)), Decimal(m.group(2))
    if not lo < hi:
        raise AgrTextError(f"{printed!r}: {lo} is not below {hi}")
    return lo, hi


def verify_figure(page: str) -> None:
    """Figure 4.4's title, axis label, legend and note, and each year's block of five whole lines, in order."""
    missing = [t for t in FIGURE_44_TEXTS if not textmatch.contains(page, t)]
    if missing:
        raise AgrTextError(f"not found on PDF page {FIGURE_44_PAGE}: {missing}")
    lines = [" ".join(ln.split()) for ln in page.splitlines()]
    at = 0
    for y in FIGURE_44:
        want = y.lines
        found = next((i for i in range(at, len(lines) - 4) if lines[i : i + 5] == want), None)
        if found is None:
            raise AgrTextError(f"Figure 4.4's labels for {y.year} {want} are not five consecutive lines on the page")
        at = found + 5
        parts = Decimal(y.adaptation) + Decimal(y.mitigation) + Decimal(y.cross_cutting)
        if abs(parts - Decimal(y.total)) > Decimal("0.15"):
            raise AgrTextError(f"{y.year}: {y.adaptation} + {y.mitigation} + {y.cross_cutting} is not {y.total}")
    if FIGURE_44[-1].year != "2023" or number(FLOWS_2023_TEXT.value) != Decimal(FIGURE_44[-1].adaptation):
        raise AgrTextError("the 2023 adaptation label does not equal the 2023 value stated in the text")


def _step_found(f: InputFile, statements: list[Statement], what: str) -> str:
    pages = sorted({(s.page, s.printed_page) for s in statements})
    where = ", ".join(f"PDF p. {page} (printed {printed})" for page, printed in pages)
    quoted = " ".join(f'"{s.sentence}"' for s in statements)
    return (
        f"Read the text of UNEP's {what} (sha256 {f.snapshot.sha256[:12]}…, downloaded by hand from UNEP's repository; "
        f"see the snapshot note) and found these sentences, each with its value as printed, on {where} before "
        f"publishing: {quoted}"
    )


# --- indicators ----------------------------------------------------------------------------------------------------

USD_BN_YEAR = Unit(
    code="USD-bn-2023-per-year",
    label="billion US dollars a year (constant 2023 prices)",
    short="US$ bn/yr",
)
_LINES = Dimension(
    id="line-of-evidence",
    label="Line of evidence",
    values=[
        DimensionValue(id="modelled-costs", label="Modelled costs of adaptation, by 2035"),
        DimensionValue(
            id="finance-needs",
            label="Finance needs in national adaptation plans and NDCs, 2023–2035",
        ),
    ],
)
_ENDS = Dimension(
    id="end",
    label="End of the printed range",
    values=[DimensionValue(id="low", label="Low end"), DimensionValue(id="high", label="High end")],
)
_GEOGRAPHY = "Developing countries, as grouped by UNEP's Adaptation Gap Report 2025"
_FLOWS_BASIS = (
    "International public finance for adaptation committed by developed countries (Annex II Parties to the UNFCCC) "
    "to developing countries (non-Annex I Parties), bilateral and through the developed-country share of multilateral "
    "institutions, in constant 2023 prices. Commitments, not disbursements. UNEP's figures from the OECD DAC "
    "Climate-Related Development Finance data set (recipients' perspective), counting projects with adaptation as a "
    "principal objective in full and as a significant objective at about 40 percent. Private finance mobilised, "
    "export credits and flows between developing countries are not included."
)


def _needs(files: dict[str, InputFile]) -> Result:
    f = files[REPORT.key]
    pages = pages_text(f.path, REPORT_PAGES)
    statements = [RANGE_KEY_MESSAGE, RANGE_SUMMARY, MODELLED_COSTS, FINANCE_NEEDS]
    for s in statements:
        verify(pages, s)
    lo, hi = range_ends(RANGE_KEY_MESSAGE.value)
    modelled, needs = number(MODELLED_COSTS.value), number(FINANCE_NEEDS.value)
    if range_ends(RANGE_SUMMARY.value) != (lo, hi) or (modelled, needs) != (lo, hi):
        raise AgrTextError(f"the two lines of evidence ({modelled}, {needs}) are not the ends of the range {lo}–{hi}")
    obs = [
        Observation(
            entity=ENTITY,
            period="2035",
            value=float(modelled),
            status="projection",
            note="Annual cost by 2035, from an updated modelling analysis.",
            dims={"line-of-evidence": "modelled-costs"},
        ),
        Observation(
            entity=ENTITY,
            period="2023/2035",
            value=float(needs),
            status="projection",
            note="Annual finance needs for the period 2023–2035, from national adaptation plans and NDCs "
            "extrapolated to all developing countries.",
            dims={"line-of-evidence": "finance-needs"},
        ),
    ]
    return Result(
        observations=obs,
        vintage=VINTAGE,
        steps=[
            _step_found(f, statements, "report PDF"),
            f'Published the two lines of evidence as printed: "{MODELLED_COSTS.value}" (modelled costs, by 2035) as '
            f'{modelled} and "{FINANCE_NEEDS.value}" (finance needs, 2023–2035) as {needs}. They are the two ends of '
            f'the report\'s plausible central range, "{RANGE_KEY_MESSAGE.value}" (also on p. xiii), which is not '
            "published as a midpoint.",
        ],
        published_value=PublishedValueRef(
            document=SOURCE,
            locator=f"Chapter 4, key messages, {RANGE_KEY_MESSAGE.locator}",
            quote=f"{RANGE_KEY_MESSAGE.sentence}: {MODELLED_COSTS.sentence} {FINANCE_NEEDS.sentence}",
        ),
    )


def _flows(files: dict[str, InputFile]) -> Result:
    f, a = files[REPORT.key], files[ANNEXES.key]
    pages = pages_text(f.path, REPORT_PAGES)
    annex = pages_text(a.path, ANNEX_PAGES)
    for s in (FLOWS_2023_TEXT, FLOWS_FOREWORD, OECD_IN_REPORT):
        verify(pages, s)
    for s in (OECD_IN_ANNEX, COMMITMENTS_IN_ANNEX):
        verify(annex, s)
    verify_figure(pages[FIGURE_44_PAGE - 1])
    obs = [Observation(entity=ENTITY, period=y.year, value=float(Decimal(y.adaptation))) for y in FIGURE_44]
    labels = ", ".join(f"{y.year} {y.adaptation}" for y in FIGURE_44)
    return Result(
        observations=obs,
        vintage=VINTAGE,
        steps=[
            _step_found(f, [FLOWS_2023_TEXT, FLOWS_FOREWORD, OECD_IN_REPORT], "report PDF"),
            f"Figure 4.4 (PDF p. {FIGURE_44_PAGE}, printed 47) prints its data labels as text. For each year the "
            "page's text holds five consecutive lines: adaptation, mitigation and cross-cutting commitments, their "
            "total, and the year, in the order of the figure's legend. Found the figure's title, axis label, legend "
            "and note and every year's five lines, checked that each total equals its three parts within the "
            "rounding of one-decimal labels, and that the 2023 adaptation label equals the "
            f'"{FLOWS_2023_TEXT.value}" stated in the text of the same page. Published the adaptation labels as '
            f"printed (US$ billion): {labels}. Nothing was measured from the bars.",
            f'Origin of the numbers: the report says the flows analysis is "based on data from the Organisation for '
            f'Economic Co-operation and Development (OECD)" (p. 46), and its online annex 4.B (annexes PDF sha256 '
            f"{a.snapshot.sha256[:12]}…, PDF p. {OECD_IN_ANNEX.page}, printed {OECD_IN_ANNEX.printed_page}) says: "
            f'"{OECD_IN_ANNEX.sentence} {COMMITMENTS_IN_ANNEX.sentence}" UNEP applied the coefficients and the '
            "developed-country shares of multilateral finance; the values are UNEP's, under UNEP's notice.",
        ],
        published_value=PublishedValueRef(
            document=SOURCE,
            locator=f"Figure 4.4 and section 4.3.2, {FLOWS_2023_TEXT.locator}",
            quote=FLOWS_2023_TEXT.sentence,
        ),
        origin_meta={ANNEXES.key: OriginMeta(url_main=ANNEXES_PAGE)},
    )


def _flows_2023(files: dict[str, InputFile]) -> Result:
    f = files[REPORT.key]
    pages = pages_text(f.path, REPORT_PAGES)
    statements = [FLOWS_2023_SUMMARY, FLOWS_2023_KEY_MESSAGE]
    for s in statements:
        verify(pages, s)
    value = number(FLOWS_2023_SUMMARY.value.split(" in ")[0])
    if number(FLOWS_2023_KEY_MESSAGE.value.split(" in ")[0]) != value:
        raise AgrTextError("the executive summary and the key messages state different 2023 flows")
    return Result(
        observations=[Observation(entity=ENTITY, period="2023", value=float(value))],
        vintage=VINTAGE,
        steps=[
            _step_found(f, statements, "report PDF"),
            f'Published "{FLOWS_2023_SUMMARY.value}" as {value} billion US dollars for 2023, the rounded figure the '
            "report compares with needs. The unrounded 2023 value of Figure 4.4 is in "
            "adaptation-finance.unep-agr-2025.international-public-flows.",
        ],
        published_value=PublishedValueRef(
            document=SOURCE,
            locator=f"Executive summary, {FLOWS_2023_SUMMARY.locator}",
            quote=FLOWS_2023_SUMMARY.sentence,
        ),
    )


def _ratio(files: dict[str, InputFile]) -> Result:
    f = files[REPORT.key]
    pages = pages_text(f.path, REPORT_PAGES)
    statements = [RATIO_KEY_MESSAGE, RATIO_SUMMARY, RATIO_WITH_PRIVATE]
    for s in statements:
        verify(pages, s)
    lo, hi = range_ends(RATIO_KEY_MESSAGE.value)
    if range_ends(RATIO_SUMMARY.value) != (lo, hi):
        raise AgrTextError("the executive summary and the key messages state different ratios")
    return Result(
        observations=[
            Observation(entity=ENTITY, period="2035", value=float(v), status="projection", dims={"end": end})
            for end, v in (("low", lo), ("high", hi))
        ],
        vintage=VINTAGE,
        steps=[
            _step_found(f, statements, "report PDF"),
            f'Published the range "{RATIO_KEY_MESSAGE.value}" as its two ends, {lo} and {hi}, as printed. The report '
            "compares adaptation costs and needs by 2035 with international public adaptation finance in 2023; it "
            f'says the ratio would be "{RATIO_WITH_PRIVATE.value}" as much if private finance mobilised from '
            "international public finance were included (p. 50, note 12), which is not published here.",
        ],
        published_value=PublishedValueRef(
            document=SOURCE,
            locator=f"Chapter 4, key messages, {RATIO_KEY_MESSAGE.locator}",
            quote=RATIO_KEY_MESSAGE.sentence,
        ),
    )


def _foreword_check(period: str, stated: str) -> PublisherCheck:
    return PublisherCheck(
        source_id=SOURCE,
        vintage=VINTAGE,
        entity=ENTITY,
        period=period,
        stated=stated,
        quote=FLOWS_FOREWORD.sentence,
        url=REPORT_URL,
    )


def transforms(paths: Paths) -> list[Transform]:
    here = Path(__file__)
    return [
        Transform(
            spec=Spec(
                id="adaptation-finance.unep-agr-2025.needs-2035",
                title="What adapting to climate change will cost developing countries each year by 2035",
                description="UNEP's estimate of what developing countries will need each year by 2035 to adapt to "
                "climate change, from two lines of evidence that are the ends of its plausible central range: "
                "modelled costs of adaptation, and the finance needs countries state in their national adaptation "
                "plans and nationally determined contributions, extrapolated to all developing countries. In billion "
                "US dollars a year at constant 2023 prices, not adjusted for inflation to 2035.",
                kind="published-value",
                unit=USD_BN_YEAR,
                display=Display(decimals=0),
                scope=Scope(
                    geography=_GEOGRAPHY,
                    basis="Annual costs of adaptation (modelled, by 2035) and adaptation finance needs (national "
                    "plans and NDCs, 2023–2035), constant 2023 prices, not inflation-adjusted.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                dimensions=(_LINES,),
                headline_dims=(("line-of-evidence", "modelled-costs"),),
            ),
            inputs=(REPORT,),
            run=_needs,
            module_file=here,
            validation=Validation(min_rows=2, value_range=(1.0, 2_000.0)),
        ),
        Transform(
            spec=Spec(
                id="adaptation-finance.unep-agr-2025.international-public-flows",
                title="International public finance for adaptation from developed to developing countries",
                description="How much international public finance developed countries committed each year to help "
                "developing countries adapt to climate change, 2019 to 2023, in billion US dollars at constant 2023 "
                "prices, as tracked by UNEP from OECD data.",
                kind="published-value",
                unit=Unit(
                    code="USD-bn-2023",
                    label="billion US dollars (constant 2023 prices)",
                    short="US$ bn",
                ),
                display=Display(decimals=1),
                scope=Scope(geography=_GEOGRAPHY, basis=_FLOWS_BASIS),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(REPORT, ANNEXES),
            run=_flows,
            module_file=here,
            validation=Validation(min_rows=len(FIGURE_44), value_range=(1.0, 200.0)),
            checks=(_foreword_check("2022", "28"), _foreword_check("2023", "26")),
        ),
        Transform(
            spec=Spec(
                id="adaptation-finance.unep-agr-2025.flows-2023",
                title="International public finance for adaptation in 2023, as the report rounds it",
                description="International public finance committed by developed countries to help developing "
                "countries adapt in 2023, in billion US dollars at constant 2023 prices, as the Adaptation Gap Report "
                "2025 states it when comparing it with needs.",
                kind="published-value",
                unit=Unit(
                    code="USD-bn-2023",
                    label="billion US dollars (constant 2023 prices)",
                    short="US$ bn",
                ),
                display=Display(decimals=0),
                scope=Scope(geography=_GEOGRAPHY, basis=_FLOWS_BASIS),
                geo_coverage="global-only",
                headline_entity=ENTITY,
            ),
            inputs=(REPORT,),
            run=_flows_2023,
            module_file=here,
            validation=Validation(min_rows=1, value_range=(1.0, 200.0)),
        ),
        Transform(
            spec=Spec(
                id="adaptation-finance.unep-agr-2025.needs-to-flows-ratio",
                title="How many times adaptation needs exceed international public adaptation finance",
                description="UNEP's comparison of what developing countries will need each year by 2035 to adapt "
                "with the international public adaptation finance they received in 2023: needs are 12 to 14 times "
                "the flows, as printed in the report.",
                kind="published-value",
                unit=Unit(code="times", label="times as much as international public flows", short="×"),
                display=Display(decimals=0),
                scope=Scope(
                    geography=_GEOGRAPHY,
                    basis="Annual adaptation costs and finance needs by 2035 (constant 2023 prices) divided by "
                    "international public adaptation finance flows in 2023, as stated by UNEP; private finance "
                    "mobilised is not included.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                dimensions=(_ENDS,),
                headline_dims=(("end", "low"),),
            ),
            inputs=(REPORT,),
            run=_ratio,
            module_file=here,
            validation=Validation(min_rows=2, value_range=(1.0, 100.0)),
        ),
    ]
