"""UNEP Adaptation Gap Report 2025 (unep-agr-2025), and the class of every entry carrying UNEP's standard notice.

No fixtures: the report and its annexes are PDFs that cannot be sliced into valid PDFs, and UNEP's notice does not
allow re-hosting them (mirror_raw false). Tests that read them are marked snapshot and read the files a person
downloaded and recorded with envdash snapshot add (see pipeline/sources/unep-agr-2025.yaml); the others check the
registry and the declared statements themselves.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from envdash import snapshots
from envdash.paths import Paths
from envdash.registry import load_registry
from envdash.transform import InputFile, run_checks, validate
from envdash.transforms.action import unep_agr as agr

UNEP = ("unep-agr-2025", "unep-egr-2025", "unep-food-waste-index-2024")
IDS = {
    "adaptation-finance.unep-agr-2025.needs-2035",
    "adaptation-finance.unep-agr-2025.international-public-flows",
    "adaptation-finance.unep-agr-2025.flows-2023",
    "adaptation-finance.unep-agr-2025.needs-to-flows-ratio",
}
STATEMENTS = [v for v in vars(agr).values() if isinstance(v, agr.Statement)]


# --- registry ------------------------------------------------------------------------------------------------------


def test_every_unep_notice_entry_is_noncommercial_and_not_mirrored():
    reg = load_registry(Paths.default())
    entries = [reg.sources[s] for s in UNEP]
    for s in entries:
        assert s.licence_class == "noncommercial", s.id
        assert s.obligations.mirror_raw is False and s.acquisition == "manual"
        assert s.evidence.terms_check == "manual"
        assert "for publicity or advertising is not permitted" in (s.obligations.notice or "")
    assert len({s.licence.name for s in entries}) == 1
    assert len({s.evidence.licence_quote for s in entries}) == 1


def test_agr_registers_the_report_and_its_annexes_as_manual_files():
    src = load_registry(Paths.default()).sources[agr.SOURCE]
    assert [(a.id, a.url, a.format) for a in src.artifacts] == [
        ("report-pdf", None, "pdf"),
        ("online-annexes-pdf", None, "pdf"),
    ]
    assert "7aae2efd6169f64163c6e4624df3d0b1754a9ba26493cc0060b77420e73f79cf" in src.artifacts[0].description


# --- declared statements -------------------------------------------------------------------------------------------


def test_each_value_phrase_is_part_of_its_sentence():
    assert len(STATEMENTS) >= 14
    for s in STATEMENTS:
        assert s.value in s.sentence, s


def test_declared_values():
    assert agr.range_ends(agr.RANGE_KEY_MESSAGE.value) == (Decimal(310), Decimal(365))
    assert (agr.number(agr.MODELLED_COSTS.value), agr.number(agr.FINANCE_NEEDS.value)) == (310, 365)
    assert agr.range_ends(agr.RATIO_KEY_MESSAGE.value) == (12, 14)
    assert [(y.year, y.adaptation) for y in agr.FIGURE_44] == [
        ("2019", "19.8"),
        ("2020", "24.7"),
        ("2021", "21.3"),
        ("2022", "27.9"),
        ("2023", "25.9"),
    ]
    assert agr.number(agr.FLOWS_2023_TEXT.value) == Decimal(agr.FIGURE_44[-1].adaptation)


def test_specs():
    ts = {t.spec.id: t for t in agr.transforms(Paths.default())}
    assert set(ts) == IDS
    for t in ts.values():
        assert t.spec.headline_entity == agr.ENTITY == "UNEP_AGR_DEV" and t.spec.geo_coverage == "global-only"
    assert [i.key for i in ts["adaptation-finance.unep-agr-2025.international-public-flows"].inputs] == [
        "unep-agr-2025/report-pdf",
        "unep-agr-2025/online-annexes-pdf",
    ]
    checks = ts["adaptation-finance.unep-agr-2025.international-public-flows"].checks
    assert [(c.period, c.stated) for c in checks] == [("2022", "28"), ("2023", "26")]


# --- the downloaded PDFs -------------------------------------------------------------------------------------------


def _files() -> dict[str, InputFile]:
    p = Paths.default()
    cur = snapshots.read_current(p)
    out = {}
    for i in (agr.REPORT, agr.ANNEXES):
        snap = snapshots.read_manifest(p, cur[i.key])
        assert snap is not None
        out[i.key] = InputFile(snapshots.cache_path(p, snap.sha256), snap)
    return out


@pytest.mark.snapshot
def test_builds_from_the_downloaded_report():
    files = _files()
    got = {}
    for t in agr.transforms(Paths.default()):
        r = t.run({i.key: files[i.key] for i in t.inputs})
        validate(t, r.observations)
        assert all(c.status == "pass" for c in run_checks(t, {agr.SOURCE: r.vintage}, r.observations))
        got[t.spec.id] = [(o.period, o.value, o.dims) for o in r.observations]
    assert got["adaptation-finance.unep-agr-2025.needs-2035"] == [
        ("2035", 310.0, {"line-of-evidence": "modelled-costs"}),
        ("2023/2035", 365.0, {"line-of-evidence": "finance-needs"}),
    ]
    assert got["adaptation-finance.unep-agr-2025.international-public-flows"] == [
        ("2019", 19.8, {}),
        ("2020", 24.7, {}),
        ("2021", 21.3, {}),
        ("2022", 27.9, {}),
        ("2023", 25.9, {}),
    ]
    assert got["adaptation-finance.unep-agr-2025.flows-2023"] == [("2023", 26.0, {})]
    assert got["adaptation-finance.unep-agr-2025.needs-to-flows-ratio"] == [
        ("2035", 12.0, {"end": "low"}),
        ("2035", 14.0, {"end": "high"}),
    ]


@pytest.mark.snapshot
def test_values_must_be_printed_as_declared():
    files = _files()
    pages = agr.pages_text(files[agr.REPORT.key].path, agr.REPORT_PAGES)

    def edited(page: int, old: str, new: str) -> list[str]:
        assert old in pages[page - 1]
        return ["" if i != page - 1 else pages[i].replace(old, new) for i in range(len(pages))]

    for s in STATEMENTS:
        if s is not agr.OECD_IN_ANNEX and s is not agr.COMMITMENTS_IN_ANNEX:
            agr.verify(pages, s)
    # A digit before the range, or the same digits split another way: textmatch alone ignores the dash.
    with pytest.raises(agr.AgrTextError, match="printed as such"):
        agr.verify(edited(58, "12–14 times", "121–4 times"), agr.RATIO_KEY_MESSAGE)
    with pytest.raises(agr.AgrTextError, match="printed as such"):
        agr.verify(edited(58, "US$365 billion/year", "US$36 5 billion/year"), agr.FINANCE_NEEDS)
    with pytest.raises(agr.AgrTextError, match="not found on PDF page 58"):
        agr.verify(edited(58, "US$365 billion/year", "US$356 billion/year"), agr.FINANCE_NEEDS)
    # Figure 4.4: a label moved within its year's block, or a changed label, stops the flows.
    figure = pages[agr.FIGURE_44_PAGE - 1]
    agr.verify_figure(figure)
    with pytest.raises(agr.AgrTextError, match="2019"):
        agr.verify_figure(figure.replace("19.8\n34.7", "34.7\n19.8"))
    with pytest.raises(agr.AgrTextError, match="2023"):
        agr.verify_figure(figure.replace("25.9\n58.1", "25.8\n58.1"))


@pytest.mark.snapshot
def test_annex_names_the_oecd_data_set():
    files = _files()
    annex = agr.pages_text(files[agr.ANNEXES.key].path, agr.ANNEX_PAGES)
    agr.verify(annex, agr.OECD_IN_ANNEX)
    agr.verify(annex, agr.COMMITMENTS_IN_ANNEX)
