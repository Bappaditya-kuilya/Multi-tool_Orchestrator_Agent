from __future__ import annotations

import time

import pytest
from pathlib import Path
import yaml

from src.semantic import SemanticMatcher
from src.router import Router, NoToolForCapability
from src.registry import ToolRegistry
from src.models import ToolManifest


@pytest.fixture
def semantic_matcher():
    docs = [
        "mock-weather weather",
        "mock-wikipedia wikipedia",
        "mock-calculator calculator",
        "mock-github-search github-search",
    ]
    return SemanticMatcher(docs)


def test_exact_match(semantic_matcher):
    ranked = semantic_matcher.rank("weather", [
        "mock-weather weather",
        "mock-wikipedia wikipedia",
        "mock-calculator calculator",
    ])
    assert ranked[0][0] == "mock-weather weather"


def test_semantic_similarity(semantic_matcher):
    ranked = semantic_matcher.rank("temperature", [
        "mock-weather weather",
        "mock-wikipedia wikipedia",
        "mock-calculator calculator",
    ])
    assert ranked[0][0] == "mock-weather weather"


def test_fuzzy_match(semantic_matcher):
    ranked = semantic_matcher.rank("calc", [
        "mock-weather weather",
        "mock-wikipedia wikipedia",
        "mock-calculator calculator",
    ])
    assert ranked[0][0] == "mock-calculator calculator"


@pytest.fixture
def semantic_registry(tmp_path):
    reg = ToolRegistry()
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "weather.yaml").write_text(yaml.dump({
        "name": "mock-weather",
        "capability_tags": ["weather"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "required_scope": "weather:read",
        "priority": 10,
    }))
    (manifests_dir / "wiki.yaml").write_text(yaml.dump({
        "name": "mock-wikipedia",
        "capability_tags": ["wikipedia"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "required_scope": "wikipedia:read",
        "priority": 10,
    }))
    reg.load_manifests(manifests_dir)
    return reg


def test_router_exact_match(semantic_registry):
    router = Router(semantic_registry)
    tools = router.route("weather")
    assert len(tools) == 1
    assert tools[0].name == "mock-weather"


def test_router_semantic_fallback(semantic_registry):
    router = Router(semantic_registry, use_semantic=True, threshold=0.1)
    tools = router.route("temperature")
    assert len(tools) >= 1
    assert tools[0].name == "mock-weather"


def test_router_semantic_disabled_raises(semantic_registry):
    router = Router(semantic_registry, use_semantic=False)
    with pytest.raises(NoToolForCapability):
        router.route("temperature")


def test_empty_query_similarity_is_zero(semantic_matcher):
    assert semantic_matcher.similarity("", "mock-weather weather") == 0.0
    assert semantic_matcher.similarity("   ", "mock-weather weather") == 0.0
    ranked = semantic_matcher.rank("", semantic_matcher.documents)
    assert all(score == 0.0 for _, score in ranked)


def test_substring_score_prefix_semantics(semantic_matcher):
    assert semantic_matcher._substring_score("alpha beta", "a b c") == 0.3
    assert semantic_matcher._substring_score("xyz qrs", "abc def") == 0.0
    assert semantic_matcher._substring_score("abandon abacus", "ab abc") == 0.3
    assert semantic_matcher._substring_score("calculator", "calc") == 0.5


def test_rank_1000_word_query_50_docs_under_2s():
    docs = [
        " ".join(f"topic{d}word{i}" for i in range(1000))
        for d in range(50)
    ]
    query = " ".join(f"queryword{i}" for i in range(1000))
    matcher = SemanticMatcher(docs)
    start = time.monotonic()
    matcher.rank(query, docs)
    assert time.monotonic() - start < 2.0
