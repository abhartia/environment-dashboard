"""Ivanova et al. (2020): mitigation potential of household consumption options, as the article's text states it.

Input: the version-of-record PDF the authors deposited on Zenodo (record 4106717, CC BY 4.0), 20 pages including
IOP's cover page, so PDF page n is printed page n - 1.

What the article holds. The per-option statistics (mean, median, quartiles, range) for all 61 options are in
Figures 3 to 7 and in the supplementary spreadsheet ERL_15_9_093001_suppdata.xlsx. Figures 3 to 6 are JPEG images
in this PDF (no numbers can be read from them without digitising, which we do not do), and the spreadsheet is
behind IOP's bot check, so it has to be downloaded by a person (see pipeline/sources/ivanova-2020.yaml). What the
PDF does state as text is a mean, a median and/or a range for 28 of the options, in the abstract and in section 3.
This transform publishes exactly those, and nothing else.

Every value comes from a STATEMENTS entry: the verbatim sentence, the PDF page it is on, and for each value the
words inside the sentence that state it. Before publishing, the transform
- finds every sentence in the text of its page (textmatch rules: whitespace, line-break hyphens and dashes are
  ignored), except that a minus sign (U+2212) must match a minus sign, so a sign can never be lost;
- checks that each value's words are part of its sentence and that the number, as printed, is in those words;
- publishes the printed digits as the value (no rounding, no arithmetic).

Reading rules. Option names are the ones the article sets in italics (checked against the PDF's font runs on
2026-10-04). Several values listed with several options ("0.9, 0.8 and 0.7 ... respectively", "0.4 and 0.2")
are read in the order the options are named. "between A and B" is the range across the reviewed studies: the
larger number is the upper end, the smaller the lower end. A range is attached to that option's mean and median.

Where the article states the same statistic twice for one option, both must agree; if they do not, that value is
published as null with both statements as the reason (the article's abstract gives the vegan diet a median of
0.8, section 3.2 gives 0.9). The abstract's repeats are the only second statements of these values by the
producer: the vegan diet mean (0.9) and the renewable electricity median (1.6) agree with section 3. No other
statement by the authors with per-option values was found (searched 2026-10-04: the University of Leeds news
story of 14 December 2021 and the CREDS page give only the top-ten total), so there is no publisher cross-check:
one would only compare the article with itself, which the agreement rule above already does.

Statements that are left out, because they do not give one number for one option:
- abstract: transport options "with a median reduction potential of more than 1.7" (a bound, for three options);
- section 3.1: Less car transport, Shift to active transport and Shift to public transport "have an average
  mitigation potential between 0.6 and 1.0" (one span for three options);
- section 3.1: Car-pooling and car-sharing and Fuel efficient driving "have an average carbon savings of 0.3",
  section 3.2: Sustainable diet or a Shift to lower carbon meats "an average annual reduction of 0.5", and Food
  sufficiency and Food waste reduction "an average of 0.3 ... and a median of 0.1" (one number for two options:
  the text does not say whether each option has it);
- section 3.4: not having a pet and sharing "median mitigation potential around 0.3" (approximate, two options);
- section 4.1: the top ten options together, 9.2 (a total, not an option);
- section 3.3: Less living space and co-housing "up to 1.0" (only the upper end of a range; it stays in the
  value's note, and the mean of 0.3 is published).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from envdash import textmatch
from envdash.models import Dimension, DimensionValue, Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "ivanova-2020"
ARTICLE = Input(SOURCE, "article-pdf")
INDICATOR = "action.ivanova-2020.options"
VINTAGE = "Environ. Res. Lett. 15 093001 (2020)"
PUBLISHED = "2020-08-20"
PERIOD = "2020"
ENTITY = "WLD"
MINUS = "−"

Statistic = Literal["mean", "median"]
Domain = Literal["transport", "food", "housing"]

DOMAINS: dict[str, str] = {"transport": "Transport", "food": "Food", "housing": "Housing"}
STATISTICS: dict[str, str] = {"mean": "Mean of the reviewed studies", "median": "Median of the reviewed studies"}

# option id -> (domain, the option's name as the article prints it)
OPTIONS: dict[str, tuple[Domain, str]] = {
    "living-car-free": ("transport", "Living car-free"),
    "shift-to-bev": ("transport", "Shift to battery electric vehicle (BEV)"),
    "one-less-flight-long-return": ("transport", "One less flight (long return)"),
    "less-transport-by-air": ("transport", "Less transport by air"),
    "phev-hev": ("transport", "(Plug-in) hybrid electric vehicles (PHEV/HEV)"),
    "one-less-flight-medium-return": ("transport", "One less flight (medium return)"),
    "telecommuting": ("transport", "Telecommuting"),
    "energy-and-material-efficiency": ("transport", "Energy and material efficiency"),
    "fuel-cell-vehicles": ("transport", "Fuel cell vehicles (FCV)"),
    "vegan-diet": ("food", "Vegan diet"),
    "mediterranean-and-similar-diet": ("food", "Mediterranean and similar diet"),
    "improved-cooking-equipment": ("food", "Improved cooking equipment"),
    "vegetarian-diet": ("food", "Vegetarian diet"),
    "organic-food": ("food", "Organic food"),
    "regional-and-local-food": ("food", "Regional and local food"),
    "nutrition-guidelines-diets": ("food", "Nutrition guidelines diets"),
    "seasonal-and-fresh-food": ("food", "Seasonal and fresh food"),
    "food-waste-management": ("food", "Food waste management"),
    "renewable-electricity": ("housing", "Renewable electricity"),
    "producing-own-renewable-electricity": ("housing", "Producing own renewable electricity"),
    "refurbishment-and-renovation": ("housing", "Refurbishment and renovation"),
    "heat-pump": ("housing", "Heat pump"),
    "renewable-based-heating": ("housing", "Renewable-based heating"),
    "passive-house": ("housing", "Passive house"),
    "less-living-space-and-co-housing": ("housing", "Less living space and co-housing"),
    "hot-water-saving": ("housing", "Hot water saving"),
    "smart-metering": ("housing", "Smart metering"),
    "lowering-room-temperature": ("housing", "Lowering room temperature (by 1 °C to 3 °C)"),
}


@dataclass(frozen=True)
class Stated:
    option: str
    statistic: Statistic
    printed: str
    """The number exactly as printed (a minus sign is U+2212)."""
    words: str
    """The words of the sentence that state it."""


@dataclass(frozen=True)
class StatedRange:
    option: str
    high: str
    low: str
    words: str


@dataclass(frozen=True)
class Statement:
    locator: str
    parts: tuple[tuple[int, str], ...]
    """(PDF page, verbatim text) in reading order; a sentence broken by a page or a figure has two parts."""
    values: tuple[Stated, ...] = ()
    ranges: tuple[StatedRange, ...] = ()

    @property
    def quote(self) -> str:
        return " ".join(text for _, text in self.parts)


T = "tCO₂eq/cap"

STATEMENTS: tuple[Statement, ...] = (
    Statement(
        "Abstract, p. 1",
        (
            (
                2,
                "In the context of food, the highest carbon savings come from dietary changes, particularly an "
                f"adoption of vegan diet with an average and median mitigation potential of 0.9 and 0.8 {T}, "
                "respectively.",
            ),
        ),
        values=(
            Stated("vegan-diet", "mean", "0.9", "average and median mitigation potential of 0.9 and 0.8"),
            Stated("vegan-diet", "median", "0.8", "average and median mitigation potential of 0.9 and 0.8"),
        ),
    ),
    Statement(
        "Abstract, p. 1",
        (
            (
                2,
                "Shifting to renewable electricity and refurbishment and renovation are the options with the highest "
                f"mitigation potential in the housing domain, with medians at 1.6 and 0.9 {T}, respectively.",
            ),
        ),
        values=(
            Stated("renewable-electricity", "median", "1.6", "medians at 1.6 and 0.9"),
            Stated("refurbishment-and-renovation", "median", "0.9", "medians at 1.6 and 0.9"),
        ),
    ),
    Statement(
        "Section 3.1 (Transport), p. 5",
        (
            (
                6,
                f"One less flight (long return) may reduce between 4.5 and 0.7 (mean of 1.9) {T}, while taking One "
                f"less flight (medium return)—between 1.5 and 0.2 (0.6) {T}. The two options have a median "
                f"reduction potential of 1.7 and 0.6 {T}, respectively.",
            ),
        ),
        values=(
            Stated("one-less-flight-long-return", "mean", "1.9", "(mean of 1.9)"),
            Stated("one-less-flight-medium-return", "mean", "0.6", "between 1.5 and 0.2 (0.6)"),
            Stated("one-less-flight-long-return", "median", "1.7", "median reduction potential of 1.7 and 0.6"),
            Stated("one-less-flight-medium-return", "median", "0.6", "median reduction potential of 1.7 and 0.6"),
        ),
        ranges=(
            StatedRange("one-less-flight-long-return", "4.5", "0.7", "between 4.5 and 0.7"),
            StatedRange("one-less-flight-medium-return", "1.5", "0.2", "between 1.5 and 0.2"),
        ),
    ),
    Statement(
        "Section 3.1 (Transport), p. 5",
        (
            (
                6,
                "Other studies exploring partial reductions in air travel (Less transport by air) find an average "
                f"reduction potential of 0.8 {T}.",
            ),
        ),
        values=(Stated("less-transport-by-air", "mean", "0.8", "average reduction potential of 0.8"),),
    ),
    Statement(
        "Section 3.1 (Transport), p. 5",
        (
            (
                6,
                "Living car-free has the highest median mitigation potential across all of the reviewed options at "
                f"2.0 {T}, with a range between 3.6 and 0.6 {T}.",
            ),
        ),
        values=(
            Stated(
                "living-car-free",
                "median",
                "2.0",
                "median mitigation potential across all of the reviewed options at 2.0",
            ),
        ),
        ranges=(StatedRange("living-car-free", "3.6", "0.6", "range between 3.6 and 0.6"),),
    ),
    Statement(
        "Section 3.1 (Transport), p. 5",
        ((6, f"Telecommuting practices reduce commute emissions between 1.4 and 0.1 (mean of 0.4) {T},"),),
        values=(Stated("telecommuting", "mean", "0.4", "(mean of 0.4)"),),
        ranges=(StatedRange("telecommuting", "1.4", "0.1", "between 1.4 and 0.1"),),
    ),
    Statement(
        "Section 3.1 (Transport), p. 5",
        (
            (
                6,
                "The Shift to battery electric vehicle (BEV) from ICEV has mitigation potential between 5.4 and "
                f"{MINUS}1.9 {T}, with an average and median of 2.0 {T}.",
            ),
        ),
        values=(
            Stated("shift-to-bev", "mean", "2.0", "average and median of 2.0"),
            Stated("shift-to-bev", "median", "2.0", "average and median of 2.0"),
        ),
        ranges=(StatedRange("shift-to-bev", "5.4", f"{MINUS}1.9", f"between 5.4 and {MINUS}1.9"),),
    ),
    Statement(
        "Section 3.1 (Transport), p. 5",
        (
            (
                6,
                f"Carbon reduction potential varies between 3.1 and {MINUS}0.2 (mean of 0.7) {T} for (plug-in) "
                f"hybrid electric vehicles (PHEV/HEV), and between 5.8 and {MINUS}3.4 (mean of 0) {T} for fuel cell "
                "vehicles (FCV).",
            ),
        ),
        values=(
            Stated("phev-hev", "mean", "0.7", "(mean of 0.7)"),
            Stated("fuel-cell-vehicles", "mean", "0", "(mean of 0)"),
        ),
        ranges=(
            StatedRange("phev-hev", "3.1", f"{MINUS}0.2", f"between 3.1 and {MINUS}0.2"),
            StatedRange("fuel-cell-vehicles", "5.8", f"{MINUS}3.4", f"between 5.8 and {MINUS}3.4"),
        ),
    ),
    Statement(
        "Section 3.1 (Transport), p. 7",
        (
            (
                8,
                "Energy and material efficiency (e.g. more efficient combustion engine, lightweight materials, "
                "improved fuel economy, cleaner fuels) [74, 79–82] brings a reduction between 1.46 and 0.01 (mean "
                f"of 0.3) {T}.",
            ),
        ),
        values=(Stated("energy-and-material-efficiency", "mean", "0.3", "(mean of 0.3)"),),
        ranges=(StatedRange("energy-and-material-efficiency", "1.46", "0.01", "between 1.46 and 0.01"),),
    ),
    Statement(
        "Section 3.2 (Food), p. 8",
        (
            (
                9,
                "The mitigation potential associated with a diet change involving a reduction in the amount of "
                f"animal products consumed varies between 2.1 and 0.4 {T} (mean of 0.9 {T}) for a Vegan diet, "
                f"between 1.5 and 0.01 (0.5) for a Vegetarian diet, and between 2.0 and {MINUS}0.1 (0.6) for "
                "Mediterranean and similar diet—e.g. Atlantic and New Nordic. The three types of diets have median "
                f"mitigation potential of 0.9, 0.5 and 0.4 {T}, respectively.",
            ),
        ),
        values=(
            Stated("vegan-diet", "mean", "0.9", "(mean of 0.9"),
            Stated("vegetarian-diet", "mean", "0.5", "between 1.5 and 0.01 (0.5)"),
            Stated("mediterranean-and-similar-diet", "mean", "0.6", f"between 2.0 and {MINUS}0.1 (0.6)"),
            Stated("vegan-diet", "median", "0.9", "median mitigation potential of 0.9, 0.5 and 0.4"),
            Stated("vegetarian-diet", "median", "0.5", "median mitigation potential of 0.9, 0.5 and 0.4"),
            Stated(
                "mediterranean-and-similar-diet", "median", "0.4", "median mitigation potential of 0.9, 0.5 and 0.4"
            ),
        ),
        ranges=(
            StatedRange("vegan-diet", "2.1", "0.4", "between 2.1 and 0.4"),
            StatedRange("vegetarian-diet", "1.5", "0.01", "between 1.5 and 0.01"),
            StatedRange("mediterranean-and-similar-diet", "2.0", f"{MINUS}0.1", f"between 2.0 and {MINUS}0.1"),
        ),
    ),
    Statement(
        "Section 3.2 (Food), p. 8",
        (
            (
                9,
                "Nutrition guidelines diets optimized with regards to health guidelines (generally including a "
                "reduction in the red meat intake and increase in plant-based foods) are associated with more "
                f"moderate potential reductions between 1.3 and 0.01 {T} (mean of 0.3 {T}).",
            ),
        ),
        values=(Stated("nutrition-guidelines-diets", "mean", "0.3", "(mean of 0.3"),),
        ranges=(StatedRange("nutrition-guidelines-diets", "1.3", "0.01", "between 1.3 and 0.01"),),
    ),
    Statement(
        "Section 3.2 (Food), p. 9",
        (
            (
                10,
                "Improved cooking equipment is associated with strong mitigation potential amounting to a mean and a "
                f"median of 0.6 {T}.",
            ),
        ),
        values=(
            Stated("improved-cooking-equipment", "mean", "0.6", "a mean and a median of 0.6"),
            Stated("improved-cooking-equipment", "median", "0.6", "a mean and a median of 0.6"),
        ),
    ),
    Statement(
        "Section 3.2 (Food), p. 9",
        (
            (
                10,
                "Organic food have lower emissions compared to conventionally produced food, with an average annual "
                f"mitigation potential of 0.5 {T} and a median of 0.4 {T}.",
            ),
        ),
        values=(
            Stated("organic-food", "mean", "0.5", "average annual mitigation potential of 0.5"),
            Stated("organic-food", "median", "0.4", "a median of 0.4"),
        ),
    ),
    Statement(
        "Section 3.2 (Food), p. 9",
        (
            (
                10,
                "Opting for Regional and local food and Seasonal and fresh food involves average reductions of 0.4 "
                f"and 0.2 {T}.",
            ),
        ),
        values=(
            Stated("regional-and-local-food", "mean", "0.4", "average reductions of 0.4 and 0.2"),
            Stated("seasonal-and-fresh-food", "mean", "0.2", "average reductions of 0.4 and 0.2"),
        ),
    ),
    Statement(
        "Section 3.2 (Food), p. 9",
        (
            (
                10,
                "Food waste management of unavoidable food waste is associated with more modest average mitigation "
                f"potential of 0.03 {T}.",
            ),
        ),
        values=(Stated("food-waste-management", "mean", "0.03", "average mitigation potential of 0.03"),),
    ),
    Statement(
        "Section 3.3 (Housing), p. 9",
        (
            (
                10,
                "The mitigation options with the highest potential on average include purchasing Renewable "
                "electricity and Producing own renewable electricity with average values of 1.5 (ranging between "
                f"2.5 and 0.3) and 1.3 (ranging between 4.8 and 0.1) {T} (figure 5). The two options have median "
                f"mitigation potential of 1.6 and 0.6 {T}, respectively.",
            ),
        ),
        values=(
            Stated("renewable-electricity", "mean", "1.5", "average values of 1.5"),
            Stated("producing-own-renewable-electricity", "mean", "1.3", "and 1.3 (ranging"),
            Stated("renewable-electricity", "median", "1.6", "median mitigation potential of 1.6 and 0.6"),
            Stated(
                "producing-own-renewable-electricity", "median", "0.6", "median mitigation potential of 1.6 and 0.6"
            ),
        ),
        ranges=(
            StatedRange("renewable-electricity", "2.5", "0.3", "ranging between 2.5 and 0.3"),
            StatedRange("producing-own-renewable-electricity", "4.8", "0.1", "ranging between 4.8 and 0.1"),
        ),
    ),
    Statement(
        "Section 3.3 (Housing), p. 9",
        (
            (
                10,
                "Other effective infrastructure-related options associated with space heating include Refurbishment "
                "and renovation, opting for Heat pump and Renewable-based heating, which offer an average mitigation "
                f"potential of 0.9, 0.8 and 0.7 {T}, respectively.",
            ),
        ),
        values=(
            Stated("refurbishment-and-renovation", "mean", "0.9", "average mitigation potential of 0.9, 0.8 and 0.7"),
            Stated("heat-pump", "mean", "0.8", "average mitigation potential of 0.9, 0.8 and 0.7"),
            Stated("renewable-based-heating", "mean", "0.7", "average mitigation potential of 0.9, 0.8 and 0.7"),
        ),
    ),
    Statement(
        "Section 3.3 (Housing), p. 9",
        (
            (
                10,
                f"The shift to a Passive house is associated with an average reduction potential of 0.5 {T} (based "
                "on estimates by three studies), excluding GHG emissions associated with changes in infrastructure.",
            ),
        ),
        values=(Stated("passive-house", "mean", "0.5", "average reduction potential of 0.5"),),
    ),
    Statement(
        "Section 3.3 (Housing), p. 9",
        (
            (
                10,
                f"The reviewed mitigation potential of Smart metering varies between 1.1 and 0 {T}, with an average "
                f"of 0.2 {T}.",
            ),
        ),
        values=(Stated("smart-metering", "mean", "0.2", "an average of 0.2"),),
        ranges=(StatedRange("smart-metering", "1.1", "0", "between 1.1 and 0"),),
    ),
    Statement(
        "Section 3.3 (Housing), pp. 9–10",
        (
            (
                10,
                "Less living space and co-housing—which includes options such as smaller living space (and hence less",
            ),
            (
                11,
                "heating and construction), collective living with others and renting out guest rooms for other "
                f"people to live in—offer carbon reductions of up to 1.0 {T}, and an average of 0.3 {T}.",
            ),
        ),
        values=(Stated("less-living-space-and-co-housing", "mean", "0.3", "an average of 0.3"),),
    ),
    Statement(
        "Section 3.3 (Housing), p. 10",
        (
            (
                11,
                "Other behavioral interventions such as Hot water saving and Lowering room temperature by 1 °C–3 °C "
                f"bring about an average saving of 0.3 and 0.1 {T}, respectively.",
            ),
        ),
        values=(
            Stated("hot-water-saving", "mean", "0.3", "average saving of 0.3 and 0.1"),
            Stated("lowering-room-temperature", "mean", "0.1", "average saving of 0.3 and 0.1"),
        ),
    ),
)


class IvanovaTextError(ValueError):
    pass


def _key(text: str) -> str:
    """textmatch's match key, except that a minus sign survives (as a private-use character) and the ring the PDF's
    text layer uses for the degree sign reads as a degree sign."""
    t = unicodedata.normalize("NFKC", text).replace(MINUS, "").replace("◦", "°")
    return textmatch.match_key(t)


def _number_in(printed: str, words: str) -> bool:
    return re.search(rf"(?<![\d.{MINUS}]){re.escape(printed)}(?!\d)", words) is not None


def verify(pages: list[str], statements: tuple[Statement, ...] = STATEMENTS) -> None:
    """Every sentence on its page; every value's words in its sentence; every number in its words."""
    page_keys = [_key(p) for p in pages]
    problems: list[str] = []
    for s in statements:
        for page, text in s.parts:
            if not 1 <= page <= len(pages):
                problems.append(f"{s.locator}: the PDF has {len(pages)} pages; page {page} does not exist")
            elif _key(text) not in page_keys[page - 1]:
                problems.append(f"{s.locator}: not found on PDF page {page}: {text[:70]!r}...")
        for v in s.values:
            if v.option not in OPTIONS:
                problems.append(f"{s.locator}: unknown option {v.option!r}")
            if v.words not in s.quote or not _number_in(v.printed, v.words):
                problems.append(f"{s.locator}: {v.option} {v.statistic} {v.printed!r} is not stated by {v.words!r}")
        for r in s.ranges:
            if r.words not in s.quote or not (_number_in(r.high, r.words) and _number_in(r.low, r.words)):
                problems.append(f"{s.locator}: {r.option} range {r.low}..{r.high} is not stated by {r.words!r}")
            elif _num(r.low) > _num(r.high):
                problems.append(f"{s.locator}: {r.option} range low {r.low} is above high {r.high}")
    if problems:
        raise IvanovaTextError("; ".join(problems))


def _num(printed: str) -> Decimal:
    return Decimal(printed.replace(MINUS, "-"))


def _as_printed(printed: str) -> str:
    return printed.replace(MINUS, "-")


def observations(statements: tuple[Statement, ...] = STATEMENTS) -> list[Observation]:
    """The published values, in OPTIONS order then mean before median. Call verify() first."""
    stated: dict[tuple[str, str], list[tuple[Stated, Statement]]] = defaultdict(list)
    ranges: dict[str, list[tuple[StatedRange, Statement]]] = defaultdict(list)
    for s in statements:
        for v in s.values:
            stated[(v.option, v.statistic)].append((v, s))
        for r in s.ranges:
            ranges[r.option].append((r, s))
    obs: list[Observation] = []
    for option, (domain, _) in OPTIONS.items():
        rng = ranges.get(option, [])
        if len({(_num(r.low), _num(r.high)) for r, _ in rng}) > 1:
            raise IvanovaTextError(f"{option}: the article states more than one range; add a rule before publishing")
        lower = upper = None
        if rng:
            lower, upper = float(_num(rng[0][0].low)), float(_num(rng[0][0].high))
        for statistic in STATISTICS:
            found = stated.get((option, statistic), [])
            if not found:
                continue
            said_in: list[Statement] = []
            for st in [s for _, s in found] + [s for _, s in rng]:
                if all(st is not seen for seen in said_in):
                    said_in.append(st)
            note = " / ".join(f'{st.locator}: "{st.quote}"' for st in said_in)
            dims = {"domain": domain, "option": option, "statistic": statistic}
            values = {_num(v.printed) for v, _ in found}
            if len(values) > 1:
                said = "; ".join(f"{_as_printed(v.printed)} in {s.locator}" for v, s in found)
                obs.append(
                    Observation(
                        entity=ENTITY,
                        period=PERIOD,
                        value=None,
                        missing_reason=f"The article states different {statistic}s for this option: {said}. The "
                        "supplementary spreadsheet, which would settle it, has not been acquired.",
                        note=note,
                        dims=dims,
                    )
                )
                continue
            value = float(values.pop())
            in_range = lower is not None and upper is not None and lower <= value <= upper
            obs.append(
                Observation(
                    entity=ENTITY,
                    period=PERIOD,
                    value=value,
                    lower=lower if in_range else None,
                    upper=upper if in_range else None,
                    interval="range" if in_range else None,
                    note=note,
                    dims=dims,
                )
            )
            if lower is not None and not in_range:
                raise IvanovaTextError(f"{option} {statistic} {value} lies outside its stated range {lower}..{upper}")
    return obs


def _run(files: dict[str, InputFile]) -> Result:
    f = files[ARTICLE.key]
    pages = textmatch.pdf_pages_text(f.path.read_bytes())
    verify(pages)
    obs = observations()
    n_options = len({o.dims["option"] for o in obs})
    headline = next(s for s in STATEMENTS if any(v.option == "living-car-free" for v in s.values))
    return Result(
        observations=obs,
        vintage=VINTAGE,
        date_published=PUBLISHED,
        steps=[
            f"Read the text of the article's version-of-record PDF (sha256 {f.snapshot.sha256[:12]}…, the copy the "
            "authors deposited on Zenodo). Found each of "
            f"{len(STATEMENTS)} sentences from the abstract and section 3 word for word on its page before "
            "publishing; a minus sign had to match a minus sign.",
            f"Published the mean, the median and the range across the reviewed studies for the {n_options} "
            "options whose values the text states, exactly as printed. Values listed with several options are read "
            "in the order the options are named; 'between A and B' is the range across studies. Each value's "
            "sentence is in its note.",
            "Left out statements that give one number for several options, a bound ('more than', 'up to'), an "
            "approximate value ('around') or a total; the other 33 of the 61 options are only in the article's "
            "figures and its supplementary spreadsheet. Where the article states one value twice with different "
            "numbers, the value is null and both statements are given.",
        ],
        published_value=PublishedValueRef(document=SOURCE, locator=headline.locator, quote=headline.quote),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Emission cuts from household consumption options (Ivanova et al. 2020)",
                description="How much each of 28 household consumption options cut greenhouse gas emissions per "
                "person per year in the studies reviewed by Ivanova et al. (2020): the mean, the median and the "
                "range across studies, for the options whose values the article's text states. The values mostly "
                "come from high-income settings, depend on context (the electricity mix, the car replaced, the "
                "starting diet) and do not add up across options.",
                kind="published-value",
                unit=Unit(
                    code="tCO2e-per-capita-per-year",
                    label="tonnes of CO₂-equivalent per person per year",
                    short="t CO₂e/person/yr",
                ),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Studies reviewed worldwide, mostly from high-income countries",
                    basis="Meta-review of 53 studies published after 2011 (search of 24 May 2019); the period is the "
                    "year the review was published. The statistics are across the reviewed studies' estimates for "
                    "each option, not a measurement of any population. Negative values mean emissions rose.",
                ),
                geo_coverage="global-only",
                headline_entity=ENTITY,
                dimensions=(
                    Dimension(
                        id="domain",
                        label="Consumption domain",
                        values=[DimensionValue(id=k, label=v) for k, v in DOMAINS.items()],
                    ),
                    Dimension(
                        id="option",
                        label="Consumption option",
                        values=[DimensionValue(id=k, label=label) for k, (_, label) in OPTIONS.items()],
                    ),
                    Dimension(
                        id="statistic",
                        label="Statistic",
                        values=[DimensionValue(id=k, label=v) for k, v in STATISTICS.items()],
                    ),
                ),
                headline_dims=(("domain", "transport"), ("option", "living-car-free"), ("statistic", "median")),
            ),
            inputs=(ARTICLE,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=39, value_range=(-5.0, 10.0)),
        )
    ]
