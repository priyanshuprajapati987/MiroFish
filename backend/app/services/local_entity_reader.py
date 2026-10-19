"""Local entity reader - reads entities from LocalGraphStorage, no Zep API needed.

Drops into the ZepEntityReader interface so simulation prepare, profile
generation and config generation work with USE_LOCAL_STORAGE=true.
"""

import os
from typing import Dict, Any, List, Optional

from ..config import Config
from ..utils.logger import get_logger
from ..utils.local_storage import get_local_storage

logger = get_logger('mirofish.local_entity_reader')

# Node types that are graph scaffolding, not simulation entities
_SCAFFOLDING_TYPES = {"graph", "entity_type", "edge_type", "text_chunk"}


class LocalEntityReader:
    """Local file-based replacement for ZepEntityReader."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            from ..utils.local_storage import LocalGraphStorage
            self.storage = LocalGraphStorage(storage_dir)
        else:
            self.storage = get_local_storage()

    @staticmethod
    def _to_node_dict(node: Dict[str, Any]) -> Dict[str, Any]:
        """Map a local storage node to the Zep-style node dict shape."""
        node_type = node.get("type", "entity")
        raw_labels = node.get("labels")
        if raw_labels:
            labels = list(raw_labels)
        else:
            labels = ["Entity", "Node"]
            if node_type == "entity":
                entity_type = node.get("entity_type") or node.get("name")
                if entity_type:
                    labels.append(entity_type)
            elif node_type not in _SCAFFOLDING_TYPES:
                labels.append(node_type)

        return {
            "uuid": node.get("id", ""),
            "name": node.get("name") or node.get("id", ""),
            "labels": labels,
            "summary": node.get("summary") or node.get("description") or node.get("content") or "",
            "attributes": node.get("attributes") or {},
        }

    @staticmethod
    def _to_edge_dict(edge: Dict[str, Any]) -> Dict[str, Any]:
        """Map a local storage edge to the Zep-style edge dict shape."""
        return {
            "uuid": edge.get("id", ""),
            "name": edge.get("name") or edge.get("type") or "RELATED_TO",
            "fact": edge.get("fact") or edge.get("description") or "",
            "source_node_uuid": edge.get("source", ""),
            "target_node_uuid": edge.get("target", ""),
            "attributes": edge.get("attributes") or {},
        }

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"[local] 获取图谱 {graph_id} 的所有节点...")
        graph = self.storage._load_graph(graph_id)
        nodes_data = [self._to_node_dict(n) for n in graph.get("nodes", [])]
        logger.info(f"[local] 共获取 {len(nodes_data)} 个节点")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"[local] 获取图谱 {graph_id} 的所有边...")
        graph = self.storage._load_graph(graph_id)
        edges_data = [self._to_edge_dict(e) for e in graph.get("edges", [])]
        logger.info(f"[local] 共获取 {len(edges_data)} 条边")
        return edges_data

    def get_node_edges(
        self,
        node_uuid: str,
        *,
        graph_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not graph_id:
            logger.warning(f"[local] get_node_edges called without graph_id for node {node_uuid}")
            return []
        try:
            edges = self.storage.get_edges_for_node(graph_id, node_uuid)
            return [self._to_edge_dict(e) for e in edges]
        except Exception as e:
            logger.error(f"[local] 获取节点 {node_uuid} 的边失败: {e}")
            raise

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ):
        from .zep_entity_reader import EntityNode, FilteredEntities

        logger.info(f"[local] 开始筛选图谱 {graph_id} 的实体...")

        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []

        node_map = {n["uuid"]: n for n in all_nodes}

        filtered_entities = []
        entity_types_found = set()

        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]

            if not custom_labels:
                continue

            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })

                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(
            f"[local] 筛选完成: 总节点 {total_count}, 符合条件 {len(filtered_entities)}, "
            f"实体类型: {entity_types_found}"
        )

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str,
    ):
        from .zep_entity_reader import EntityNode

        node_raw = self.storage.get_node(graph_id, entity_uuid)
        if not node_raw:
            return None

        node = self._to_node_dict(node_raw)
        edges = self.get_node_edges(entity_uuid, graph_id=graph_id)
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n["uuid"]: n for n in all_nodes}

        related_edges = []
        related_node_uuids = set()

        for edge in edges:
            if edge["source_node_uuid"] == entity_uuid:
                related_edges.append({
                    "direction": "outgoing",
                    "edge_name": edge["name"],
                    "fact": edge["fact"],
                    "target_node_uuid": edge["target_node_uuid"],
                })
                related_node_uuids.add(edge["target_node_uuid"])
            else:
                related_edges.append({
                    "direction": "incoming",
                    "edge_name": edge["name"],
                    "fact": edge["fact"],
                    "source_node_uuid": edge["source_node_uuid"],
                })
                related_node_uuids.add(edge["source_node_uuid"])

        related_nodes = []
        for related_uuid in related_node_uuids:
            if related_uuid in node_map:
                related_node = node_map[related_uuid]
                related_nodes.append({
                    "uuid": related_node["uuid"],
                    "name": related_node["name"],
                    "labels": related_node["labels"],
                    "summary": related_node.get("summary", ""),
                })

        return EntityNode(
            uuid=node["uuid"],
            name=node["name"],
            labels=node["labels"],
            summary=node["summary"],
            attributes=node["attributes"],
            related_edges=related_edges,
            related_nodes=related_nodes,
        )

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ):
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities
