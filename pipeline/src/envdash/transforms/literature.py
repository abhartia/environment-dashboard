"""Published values quoted from papers and reports (pipeline/literature/<id>.yaml).

One indicator per entry, kind published-value. The build extracts the text of the snapshot's PDF page named in the
entry and refuses to publish unless the quote is found there (textmatch: whitespace, line-break hyphenation, dash
and sub/superscript differences are ignored; every letter, digit and punctuation mark must match in order). The
number itself is the entry's reading of `value_text`, a part of the quote, and is stated in the processing step.
"""

from __future__ import annotations

from pathlib import Path

from envdash import textmatch
from envdash.models import LiteratureValue, Observation, PublishedValueRef
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import Input, InputFile, Result, Spec, Transform, Validation


class QuoteNotFound(ValueError):
    pass


def verify_quote(pdf_bytes: bytes, page: int, quote: str) -> None:
    pages = textmatch.pdf_pages_text(pdf_bytes)
    if not 1 <= page <= len(pages):
        raise QuoteNotFound(f"the PDF has {len(pages)} pages; page {page} does not exist")
    if not textmatch.contains(pages[page - 1], quote):
        raise QuoteNotFound(f"quote not found on PDF page {page}: {quote[:80]!r}...")


def _make(lit: LiteratureValue, yaml_file: Path) -> Transform:
    inp = Input(lit.source_id, lit.artifact_id)

    def run(files: dict[str, InputFile]) -> Result:
        f = files[inp.key]
        verify_quote(f.path.read_bytes(), lit.pdf_page, lit.quote)
        return Result(
            observations=[
                Observation(entity=o.entity, period=o.period, value=o.value, status=o.status) for o in lit.observations
            ],
            vintage=lit.vintage,
            steps=[
                f"Quoted from {lit.locator}. The quote was found in the text of page {lit.pdf_page} of the snapshot "
                f"(sha256 {f.snapshot.sha256[:12]}…) before publishing.",
                f"Value: {lit.value_reading}",
            ],
            published_value=PublishedValueRef(document=lit.source_id, locator=lit.locator, quote=lit.quote),
        )

    return Transform(
        spec=Spec(
            id=lit.indicator_id,
            title=lit.title,
            description=lit.description,
            kind="published-value",
            unit=lit.unit,
            display=lit.display,
            scope=lit.scope,
            geo_coverage=lit.geo_coverage,
            headline_entity=lit.headline_entity,
        ),
        inputs=(inp,),
        run=run,
        module_file=Path(__file__),
        validation=Validation(min_rows=1, value_range=(-1e12, 1e12), monotonic_periods=True),
        key_files=(yaml_file,),
    )


def transforms(paths: Paths) -> list[Transform]:
    reg = load_registry(paths)
    return [_make(lit, reg.literature_files[lid]) for lid, lit in sorted(reg.literature.items())]
