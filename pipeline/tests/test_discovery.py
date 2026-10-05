"""Artifact URL discovery (envdash/discovery.py), on a real page slice; live listings under -m network."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from envdash import discovery
from envdash.fetch import make_client, resolve_url
from envdash.models import Artifact, Discover, discover_key
from envdash.paths import Paths
from envdash.registry import load_registry

from support import fixture

FIGURES = r"https://coralreefwatch\.noaa\.gov/satellite/research/figures/"


def _page():
    path, meta = fixture("noaa-crw", "global-bleaching-status")
    return path.read_text(encoding="utf-8"), meta["url"]


def _serve(pages: dict[str, str]):
    def get_text(url: str) -> str:
        return pages[url]

    return get_text


def test_links_are_absolute_without_fragments():
    page, url = _page()
    found = discovery.links(page, url)
    assert "https://www.noaa.gov/news-release/noaa-confirms-4th-global-coral-bleaching-event" in found
    # A relative link resolves against the page URL.
    assert (
        "https://coralreefwatch.noaa.gov/satellite/research/figures/"
        "ct5km_baa5-max_v3.1_tropics_nogrid_20230101to20250930.png" in found
    )
    assert len(found) == len(set(found))


def test_resolves_the_largest_key_and_records_the_listing():
    page, url = _page()
    d = Discover(
        listing_url=url,
        link_pattern=FIGURES + r"ct5km_baa5-max_v3\.1_tropics_nogrid_20230101to(?P<key>\d{8})\.png",
    )
    r = discovery.resolve(d, _serve({url: page}))
    assert r.url.endswith("_20230101to20250930.png")
    assert r.record.key == "20250930" and str(r.record.listing_url) == url and r.record.sublisting_url is None


def test_no_match_is_a_failure_not_a_guess():
    page, url = _page()
    d = Discover(listing_url=url, link_pattern=FIGURES + r"ct5km_baa5-max_v3\.1_(?P<key>\d{8})\.nc")
    with pytest.raises(discovery.DiscoveryError, match="no link"):
        discovery.resolve(d, _serve({url: page}))


def test_tie_between_different_urls_is_a_failure():
    page, url = _page()
    # The page's two news links (www.noaa.gov and www.nesdis.noaa.gov) both match, with the same key "w".
    d = Discover(listing_url=url, link_pattern=r"https://(?P<key>w)ww\.(?:noaa|nesdis\.noaa)\.gov/.*")
    with pytest.raises(discovery.DiscoveryError, match="share the largest key"):
        discovery.resolve(d, _serve({url: page}))


def test_keys_of_different_lengths_are_refused():
    page, url = _page()
    d = Discover(listing_url=url, link_pattern=r"https://www\.(?P<key>noaa|nesdis\.noaa)\.gov/.*")
    with pytest.raises(discovery.DiscoveryError, match="different lengths"):
        discovery.resolve(d, _serve({url: page}))


def test_sublisting_is_searched_newest_first():
    page, url = _page()
    # The page as its own listing: its one figure link is a "sublisting" whose text is the page again.
    fig = (
        "https://coralreefwatch.noaa.gov/satellite/research/figures/"
        "ct5km_baa5-max_v3.1_tropics_nogrid_20230101to20250930.png"
    )
    d = Discover(
        listing_url=url,
        sublisting_pattern=FIGURES + r"ct5km_baa5-max_v3\.1_tropics_nogrid_20230101to(?P<key>\d{8})\.png",
        link_pattern=r"https://www\.noaa\.gov/news-release/noaa-confirms-(?P<key>\d)th-global-coral-bleaching-event",
    )
    r = discovery.resolve(d, _serve({url: page, fig: page}))
    assert r.record.sublisting_url is not None and str(r.record.sublisting_url) == fig and r.record.key == "4"


def test_month_name_keys():
    rx = re.compile(r"https://climate\.copernicus\.eu/surface-air-temperature-(?P<month>[a-z]+)-(?P<year>\d{4})")
    assert discover_key(rx.fullmatch("https://climate.copernicus.eu/surface-air-temperature-august-2026")) == "2026-08"
    with pytest.raises(ValueError, match="not a month"):
        discover_key(rx.fullmatch("https://climate.copernicus.eu/surface-air-temperature-maps-2026"))


def test_discover_model_rules():
    with pytest.raises(ValidationError, match="named group 'key'"):
        Discover(listing_url="https://www.ncei.noaa.gov/data/snow-cover-extent/access/", link_pattern=r".*\.nc")
    with pytest.raises(ValidationError, match="not both"):
        Artifact(
            id="x",
            url="https://www.ncei.noaa.gov/data/snow-cover-extent/access/nhsce_v01r01_19661004_20260831.nc",
            format="nc",
            description="d",
            discover=Discover(
                listing_url="https://www.ncei.noaa.gov/data/snow-cover-extent/access/",
                link_pattern=r".*_(?P<key>\d{8})\.nc",
            ),
        )


DISCOVERED = ("noaaglobaltemp-v6", "c3s-era5-bulletin", "oisst-v2", "rutgers-snow-cdr")


@pytest.mark.network
@pytest.mark.parametrize("source_id", DISCOVERED)
def test_registered_listings_resolve_today(source_id):
    src = load_registry(Paths.default()).sources[source_id]
    arts = [a for a in src.artifacts if a.discover is not None]
    assert arts
    with make_client() as client:
        for art in arts:
            url, found = resolve_url(client, art)
            assert found is not None and re.fullmatch(art.discover.link_pattern, url)
            r = client.head(url)
            assert r.status_code == 200, (url, r.status_code)
