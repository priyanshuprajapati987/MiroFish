"""Local graph memory storage - No external API needed."""

from __future__ import annotations

import os
import json
import time
from typing import Any, Dict, List, Optional

from ..config import Config
from .logger import get_logger

logger = get_logger("mirofish.local_storage")

# Local storage directory
LOCAL_STORAGE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'local_storage')


class LocalGraphStorage:
    """Local file-based graph storage to replace Zep Cloud."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or LOCAL_STORAGE_DIR
        os.makedirs(self.storage_dir, exist_ok=True)
        self.graphs_dir = os.path.join(self.storage_dir, 'graphs')
        os.makedirs(self.graphs_dir, exist_ok=True)
    
    def _get_graph_path(self, graph_id: str) -> str:
        return os.path.join(self.graphs_dir, f"{graph_id}.json")
    
    def _load_graph(self, graph_id: str) -> Dict:
        path = self._get_graph_path(graph_id)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"nodes": [], "edges": [], "episodes": [], "metadata": {}}
    
    def _save_graph(self, graph_id: str, data: Dict):
        path = self._get_graph_path(graph_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def add_node(self, graph_id: str, node_id: str, node_data: Dict) -> str:
        graph = self._load_graph(graph_id)
        existing = next((n for n in graph["nodes"] if n["id"] == node_id), None)
        if existing:
            existing.update(node_data)
        else:
            node_data["id"] = node_id
            node_data["created_at"] = time.time()
            graph["nodes"].append(node_data)
        self._save_graph(graph_id, graph)
        logger.info(f"Added node {node_id} to graph {graph_id}")
        return node_id
    
    def add_edge(self, graph_id: str, source: str, target: str, edge_data: Dict) -> str:
        graph = self._load_graph(graph_id)
        edge_id = f"{source}->{target}"
        edge_data["source"] = source
        edge_data["target"] = target
        edge_data["id"] = edge_id
        edge_data["created_at"] = time.time()
        graph["edges"].append(edge_data)
        self._save_graph(graph_id, graph)
        logger.info(f"Added edge {edge_id} to graph {graph_id}")
        return edge_id
    
    def add_episode(self, graph_id: str, episode_data: Dict) -> str:
        graph = self._load_graph(graph_id)
        episode_id = f"ep_{int(time.time())}_{len(graph['episodes'])}"
        episode_data["id"] = episode_id
        episode_data["created_at"] = time.time()
        graph["episodes"].append(episode_data)
        self._save_graph(graph_id, graph)
        logger.info(f"Added episode {episode_id} to graph {graph_id}")
        return episode_id
    
    def search_nodes(self, graph_id: str, query: str, limit: int = 50) -> List[Dict]:
        graph = self._load_graph(graph_id)
        query_lower = query.lower()
        results = []
        for node in graph["nodes"]:
            node_str = json.dumps(node, ensure_ascii=False).lower()
            if query_lower in node_str:
                results.append(node)
                if len(results) >= limit:
                    break
        return results
    
    def search_edges(self, graph_id: str, query: str, limit: int = 50) -> List[Dict]:
        graph = self._load_graph(graph_id)
        query_lower = query.lower()
        results = []
        for edge in graph["edges"]:
            edge_str = json.dumps(edge, ensure_ascii=False).lower()
            if query_lower in edge_str:
                results.append(edge)
                if len(results) >= limit:
                    break
        return results
    
    def get_node(self, graph_id: str, node_id: str) -> Optional[Dict]:
        graph = self._load_graph(graph_id)
        return next((n for n in graph["nodes"] if n["id"] == node_id), None)
    
    def get_edges_for_node(self, graph_id: str, node_id: str) -> List[Dict]:
        graph = self._load_graph(graph_id)
        return [e for e in graph["edges"] if e.get("source") == node_id or e.get("target") == node_id]
    
    def get_graph_stats(self, graph_id: str) -> Dict:
        graph = self._load_graph(graph_id)
        return {
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "episode_count": len(graph["episodes"]),
            "graph_id": graph_id
        }
    
    def delete_node(self, graph_id: str, node_id: str):
        graph = self._load_graph(graph_id)
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] != node_id]
        graph["edges"] = [e for e in graph["edges"] if e.get("source") != node_id and e.get("target") != node_id]
        self._save_graph(graph_id, graph)
        logger.info(f"Deleted node {node_id} from graph {graph_id}")
    
    def clear_graph(self, graph_id: str):
        self._save_graph(graph_id, {"nodes": [], "edges": [], "episodes": [], "metadata": {}})
        logger.info(f"Cleared graph {graph_id}")
    
    def list_graphs(self) -> List[str]:
        if not os.path.exists(self.graphs_dir):
            return []
        return [f.replace('.json', '') for f in os.listdir(self.graphs_dir) if f.endswith('.json')]


# Global instance
local_storage = LocalGraphStorage()


def get_local_storage() -> LocalGraphStorage:
    """Get the local storage instance."""
    return local_storage
