"""Unit tests for the in-memory SearchIndex."""

from __future__ import annotations

from ldraw.parts import CatalogEntry, PartCategory

from pyldraw3_tui.data.search import SearchIndex, haystack


def entry(code, description, category=PartCategory.BRICK, keywords=()):
    return CatalogEntry(
        code=code,
        description=description,
        category=category,
        keywords=tuple(keywords),
    )


def index(*entries):
    return SearchIndex(entries=tuple(entries))


def test_haystack_includes_code_description_category_keywords():
    e = entry("3001", "Brick 2 x 4", PartCategory.BRICK, ["building", "rect"])
    hay = haystack(e)
    assert "3001" in hay
    assert "brick 2 x 4" in hay
    assert "brick" in hay
    assert "building" in hay
    assert hay == hay.lower()


def test_empty_query_returns_input_unchanged():
    entries = (entry("1", "One"), entry("2", "Two"))
    assert index(*entries).filter("") == list(entries)
    assert index(*entries).filter("   ") == list(entries)


def test_all_tokens_must_match():
    e1 = entry("3001", "Brick 2 x 4")
    e2 = entry("3002", "Brick 2 x 3")
    idx = index(e1, e2)
    assert idx.filter("brick 4") == [e1]
    assert idx.filter("brick nope") == []


def test_keywords_match():
    e = entry("973", "Torso", PartCategory.MINIFIG, ["body"])
    assert index(e).filter("body") == [e]


def test_ranking_order():
    exact = entry("30", "Something")
    code_prefix = entry("3001", "Also 30ish")
    desc_prefix = entry("9990", "30 Description Prefix")
    desc_sub = entry("9991", "Has 30 inside")
    other = entry("9992", "Keyword only", keywords=["ok30x"])
    idx = index(other, desc_sub, desc_prefix, code_prefix, exact)
    assert idx.filter("30") == [exact, code_prefix, desc_prefix, desc_sub, other]


def test_ties_break_by_code():
    a = entry("100", "Widget")
    b = entry("101", "Widget")
    assert index(b, a).filter("widget") == [a, b]


def test_double_spaced_descriptions_rank_naturally():
    """Real LDraw descriptions align dimensions with double spaces."""
    brick = entry("3001", "Brick  2 x  4")
    variant = entry("2434", "Brick  2 x  4 x  2 with Studs on Sides")
    slope = entry("11477", "Slope Brick Curved  2 x  1")
    results = index(slope, variant, brick).filter("brick 2 x 4")
    # Exact description first, then the prefix variant, then the rest.
    assert [e.code for e in results] == ["3001", "2434", "11477"]


def test_within_limits_scope():
    e1 = entry("3001", "Brick 2 x 4")
    e2 = entry("3002", "Brick 2 x 3")
    idx = index(e1, e2)
    assert idx.filter("brick", within=[e2]) == [e2]
    assert idx.filter("", within=[e2]) == [e2]


def test_from_catalog(parts):
    idx = SearchIndex.from_catalog(parts.catalog)
    assert len(idx.entries) == 5
    codes = [e.code for e in idx.filter("plate")]
    assert codes == ["3022", "6157"]
    assert [e.code for e in idx.filter("3001")] == ["3001"]
    # keyword search
    assert [e.code for e in idx.filter("axle")] == ["6157"]
