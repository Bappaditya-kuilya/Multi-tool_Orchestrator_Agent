import pytest

from src.router import Router, NoToolForCapability


def test_exact_match(router, sample_manifests):
    tools = router.route("calculator")
    assert len(tools) == 2
    assert all("calculator" in t.capability_tags for t in tools)


def test_no_match_raises(router):
    with pytest.raises(NoToolForCapability):
        router.route("nonexistent")


def test_multi_match_sorted_by_priority(router, sample_manifests):
    tools = router.route("calculator")
    assert len(tools) == 2
    assert tools[0].priority == 10
    assert tools[1].priority == 5