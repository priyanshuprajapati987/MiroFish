"""Tests for the local entity reader (full local mode, no Zep API)."""

import pytest

from app.config import Config
from app.services.local_entity_reader import LocalEntityReader
from app.services.zep_entity_reader import get_entity_reader
from app.utils.local_storage import LocalGraphStorage


@pytest.fixture
def storage(tmp_path):
    return LocalGraphStorage(str(tmp_path / "graphs"))


@pytest.fixture
def graph_id(storage):
    gid = "local_testgraph_0001"
    # scaffolding
    storage.add_node(gid, gid, {"type": "graph", "name": "Test Graph"})
    storage.add_node(gid, "chunk_0", {"type": "text_chunk", "content": "hello world", "index": 0})
    # entity instances (as written by local graph builder extraction)
    storage.add_node(gid, "entity_alice_1", {
        "type": "entity",
        "name": "Alice",
        "entity_type": "Student",
        "labels": ["Entity", "Student"],
        "summary": "A student in the story",
        "attributes": {"year": "2"},
    })
    storage.add_node(gid, "entity_bob_2", {
        "type": "entity",
        "name": "Bob",
        "entity_type": "Teacher",
        "labels": ["Entity", "Teacher"],
        "summary": "A teacher",
        "attributes": {},
    })
    storage.add_edge(gid, "entity_alice_1", "entity_bob_2", {
        "type": "STUDIES_UNDER",
        "name": "STUDIES_UNDER",
        "fact": "Alice studies under Bob",
    })
    return gid


def test_factory_returns_local_reader_in_local_mode(monkeypatch):
    monkeypatch.setattr(Config, "USE_LOCAL_STORAGE", True)
    reader = get_entity_reader()
    assert isinstance(reader, LocalEntityReader)


def test_local_reader_constructs_without_zep_key():
    reader = LocalEntityReader()  # must not raise ValueError
    assert reader.storage is not None


def test_get_all_nodes_and_edges(storage, graph_id):
    reader = LocalEntityReader(storage_dir=storage.storage_dir)
    nodes = reader.get_all_nodes(graph_id)
    edges = reader.get_all_edges(graph_id)

    assert len(nodes) == 4
    assert len(edges) == 1
    alice = next(n for n in nodes if n["uuid"] == "entity_alice_1")
    assert alice["name"] == "Alice"
    assert "Student" in alice["labels"]
    assert edges[0]["source_node_uuid"] == "entity_alice_1"
    assert edges[0]["target_node_uuid"] == "entity_bob_2"
    assert edges[0]["fact"] == "Alice studies under Bob"


def test_filter_defined_entities_keeps_only_typed_entities(storage, graph_id):
    reader = LocalEntityReader(storage_dir=storage.storage_dir)
    result = reader.filter_defined_entities(graph_id, enrich_with_edges=True)

    # graph meta + text_chunk scaffolding must be excluded
    assert result.filtered_count == 2
    assert result.total_count == 4
    assert result.entity_types == {"Student", "Teacher"}

    alice = next(e for e in result.entities if e.uuid == "entity_alice_1")
    assert len(alice.related_edges) == 1
    assert alice.related_edges[0]["direction"] == "outgoing"
    assert alice.related_edges[0]["edge_name"] == "STUDIES_UNDER"
    assert any(n["uuid"] == "entity_bob_2" for n in alice.related_nodes)


def test_filter_honors_defined_entity_types(storage, graph_id):
    reader = LocalEntityReader(storage_dir=storage.storage_dir)
    result = reader.filter_defined_entities(
        graph_id, defined_entity_types=["Student"], enrich_with_edges=False
    )
    assert result.filtered_count == 1
    assert result.entities[0].name == "Alice"


def test_get_entity_with_context(storage, graph_id):
    reader = LocalEntityReader(storage_dir=storage.storage_dir)
    entity = reader.get_entity_with_context(graph_id, "entity_alice_1")

    assert entity is not None
    assert entity.name == "Alice"
    assert entity.get_entity_type() == "Student"
    assert len(entity.related_edges) == 1
    assert entity.related_edges[0]["direction"] == "outgoing"
    assert any(n["uuid"] == "entity_bob_2" for n in entity.related_nodes)


def test_get_entity_with_context_missing_returns_none(storage, graph_id):
    reader = LocalEntityReader(storage_dir=storage.storage_dir)
    assert reader.get_entity_with_context(graph_id, "nope") is None


def test_get_entities_by_type(storage, graph_id):
    reader = LocalEntityReader(storage_dir=storage.storage_dir)
    teachers = reader.get_entities_by_type(graph_id, "Teacher")
    assert len(teachers) == 1
    assert teachers[0].name == "Bob"
