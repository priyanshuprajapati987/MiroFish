"""Local Zep replacement - File-based graph memory storage."""

import json
import os
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

class LocalZepClient:
    """Local file-based storage to replace Zep Cloud."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.path.join(os.path.dirname(__file__), '..', '..', 'local_storage')
        os.makedirs(self.storage_dir, exist_ok=True)
        self.graph_dir = os.path.join(self.storage_dir, 'graphs')
        os.makedirs(self.graph_dir, exist_ok=True)
    
    def _get_graph_path(self, graph_id: str) -> str:
        return os.path.join(self.graph_dir, f"{graph_id}.json")
    
    def _load_graph(self, graph_id: str) -> Dict:
        path = self._get_graph_path(graph_id)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"nodes": [], "edges": [], "episodes": []}
    
    def _save_graph(self, graph_id: str, data: Dict):
        path = self._get_graph_path(graph_id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def add_node(self, graph_id: str, node_id: str, node_data: Dict):
        graph = self._load_graph(graph_id)
        existing = next((n for n in graph["nodes"] if n["id"] == node_id), None)
        if existing:
            existing.update(node_data)
        else:
            node_data["id"] = node_id
            node_data["created_at"] = time.time()
            graph["nodes"].append(node_data)
        self._save_graph(graph_id, graph)
        return node_id
    
    def add_edge(self, graph_id: str, source: str, target: str, edge_data: Dict):
        graph = self._load_graph(graph_id)
        edge_data["source"] = source
        edge_data["target"] = target
        edge_data["created_at"] = time.time()
        graph["edges"].append(edge_data)
        self._save_graph(graph_id, graph)
        return f"{source}->{target}"
    
    def add_episode(self, graph_id: str, episode_data: Dict):
        graph = self._load_graph(graph_id)
        episode_data["created_at"] = time.time()
        episode_data["id"] = f"ep_{len(graph['episodes'])}"
        graph["episodes"].append(episode_data)
        self._save_graph(graph_id, graph)
        return episode_data["id"]
    
    def search_nodes(self, graph_id: str, query: str, limit: int = 50) -> List[Dict]:
        graph = self._load_graph(graph_id)
        query_lower = query.lower()
        results = []
        for node in graph["nodes"]:
            if any(query_lower in str(v).lower() for v in node.values()):
                results.append(node)
                if len(results) >= limit:
                    break
        return results
    
    def search_edges(self, graph_id: str, query: str, limit: int = 50) -> List[Dict]:
        graph = self._load_graph(graph_id)
        query_lower = query.lower()
        results = []
        for edge in graph["edges"]:
            if any(query_lower in str(v).lower() for v in edge.values()):
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
            "episode_count": len(graph["episodes"])
        }
    
    def delete_node(self, graph_id: str, node_id: str):
        graph = self._load_graph(graph_id)
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] != node_id]
        graph["edges"] = [e for e in graph["edges"] if e.get("source") != node_id and e.get("target") != node_id]
        self._save_graph(graph_id, graph)
    
    def clear_graph(self, graph_id: str):
        self._save_graph(graph_id, {"nodes": [], "edges": [], "episodes": []})

# Global instance
local_zep = LocalZepClient()
