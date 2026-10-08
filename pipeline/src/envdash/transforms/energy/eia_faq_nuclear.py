"""EIA FAQ 207: the generating capacity of the largest US nuclear power plant, Vogtle (Georgia), in gigawatts.

Input: the FAQ page (eia-faq-nuclear-plants/faq-207), read as the text a reader sees (envdash.textmatch, whitespace
collapsed). Two passages must be there, matched in full:
- the date of the answer: "As of <Month> <year>, the United States had <n> operating commercial nuclear power reactors
  at <n> power plants", which gives the period (year-month);
- "The Alvin W. Vogtle Electric Generating Plant in Georgia is the largest U.S. nuclear power plant. It has: Four
  reactors Total nameplate electricity generating capacity of about <MW> MW Total net summer electricity generating
  capacity of <MW> MW".
The net summer capacity is published, as a capacity (the most the plant can deliver), not an average output. EIA
states it exactly; the nameplate capacity is "about" a number, so it goes in the note only. The only change is the
unit: megawatts divided by 1,000 to give gigawatts, exactly.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from envdash import textmatch
from envdash.models import Display, Observation, PublishedValueRef, Scope, Unit
from envdash.paths import Paths
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation

SOURCE = "eia-faq-nuclear-plants"
FAQ = Input(SOURCE, "faq-207")
INDICATOR = "capacity.eia.vogtle"
ENTITY = "USA"
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
AS_OF = re.compile(
    rf"As of (?P<month>{'|'.join(MONTHS)}) (?P<year>\d{{4}}), the United States had \d+ operating commercial nuclear "
    r"power reactors at \d+ power plants"
)
VOGTLE = re.compile(
    r"The Alvin W\. Vogtle Electric Generating Plant in Georgia is the largest U\.S\. nuclear power plant\. It has: "
    r"Four reactors Total nameplate electricity generating capacity of about (?P<nameplate>\d{1,3}(?:,\d{3})*) MW "
    r"Total net summer electricity generating capacity of (?P<summer>\d{1,3}(?:,\d{3})*) MW"
)


class FaqFormatError(ValueError):
    pass


def page_text(raw: bytes, content_type: str | None, url: str | None) -> str:
    return re.sub(r"\s+", " ", textmatch.document_text(raw, content_type, url))


def read(text: str) -> tuple[str, str, str, str]:
    """(period YYYY-MM, net summer MW as printed, nameplate MW as printed, the Vogtle passage)."""
    a, v = AS_OF.findall(text), list(VOGTLE.finditer(text))
    if len(a) != 1 or len(v) != 1:
        raise FaqFormatError(
            f"expected one 'As of <month> <year>' passage and one Vogtle passage, found {len(a)} and {len(v)}: "
            "re-read the FAQ"
        )
    month, year = a[0]
    period = f"{year}-{MONTHS.index(month) + 1:02d}"
    return period, v[0]["summer"], v[0]["nameplate"], v[0].group(0)


def _run(files: dict[str, InputFile]) -> Result:
    f = files[FAQ.key]
    snap = f.snapshot
    text = page_text(f.path.read_bytes(), snap.content_type, str(snap.url) if snap.url else None)
    period, summer, nameplate, passage = read(text)
    gw = Decimal(summer.replace(",", "")) / 1000
    month = MONTHS[int(period[5:]) - 1]
    return Result(
        observations=[
            Observation(
                entity=ENTITY,
                period=period,
                value=float(gw),
                note=f"EIA's answer is dated 'As of {month} {period[:4]}'. Four reactors; EIA gives the total "
                f"nameplate capacity as about {nameplate} MW.",
            )
        ],
        vintage=f"FAQ 207, as of {month} {period[:4]}",
        steps=[
            f"Read the visible text of EIA's FAQ 207 (sha256 {snap.sha256[:12]}…) and found, in full, the passage "
            f"dating the answer ('As of {month} {period[:4]}') and the passage naming the Alvin W. Vogtle Electric "
            f"Generating Plant in Georgia as the largest US nuclear power plant, with a total net summer electricity "
            f"generating capacity of {summer} MW.",
            f"Unit conversion: {summer} megawatts divided by 1,000 gives gigawatts, exactly. This is a capacity, the "
            "most the plant can deliver in summer conditions after its own use, not its average output.",
        ],
        changes="net summer capacity converted from megawatts to gigawatts.",
        published_value=PublishedValueRef(document=SOURCE, locator="FAQ 207, answer", quote=passage),
    )


def transforms(paths: Paths) -> list[Transform]:
    return [
        Transform(
            spec=Spec(
                id=INDICATOR,
                title="Generating capacity of the largest US nuclear power plant (Vogtle)",
                description="The net summer generating capacity of the Alvin W. Vogtle Electric Generating Plant in "
                "Georgia, the largest nuclear power plant in the United States, with four reactors, in gigawatts, as "
                "stated by the US Energy Information Administration. A capacity is the most a plant can deliver, not "
                "what it delivers on average.",
                kind="published-value",
                unit=Unit(code="GW", label="gigawatts of net summer generating capacity", short="GW"),
                display=Display(decimals=2),
                scope=Scope(
                    geography="Alvin W. Vogtle Electric Generating Plant, Georgia, United States",
                    basis="Net summer capacity: the most the plant's four reactors can supply to the grid in summer "
                    "conditions, after the plant's own use. The period is the month EIA's answer is dated.",
                ),
                geo_coverage="country",
                headline_entity=ENTITY,
            ),
            inputs=(FAQ,),
            run=_run,
            module_file=Path(__file__),
            validation=Validation(min_rows=1, value_range=(1.0, 10.0)),
        )
    ]
