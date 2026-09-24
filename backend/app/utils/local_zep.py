"""Local Zep replacement - File-based graph memory storage."""

import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional


class LocalZepClient:
    """Local file-based storage to replace Zep Cloud."""

    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.path.join(os.path.dirname(__file__), '..', '..', 'local_storage')
        os.makedirs(self.storage_dir, exist_ok=True)
        self.graph_dir = os.path.join(self.storage_dir, 'graphs')
        os.makedirs(self.graph_dir, exist_ok=True)
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._lock_ttl: Dict[str, float] = {}
        self._lock_age = 3600

    def _get_lock(self, graph_id: str) -> threading.Lock:
        now = __import__('time').time()
        expired = [k for k, v in self._lock_ttl.items() if now - v > self._lock_age]
        for k in expired:
            self._locks.pop(k, None)
            self._lock_ttl.pop(k, None)
        with self._locks_guard:
            if graph_id not in self._locks:
                self._locks[graph_id] = threading.Lock()
                self._lock_ttl[graph_id] = now
            return self._locks[graph_id]

    def _get_graph_path(self, graph_id: str) -> str:
        import re
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', graph_id).strip('_') or 'unknown'
        return os.path.join(self.graph_dir, f"{safe_id}.json")

    def _load_graph(self, graph_id: str) -> Dict:
        path = self._get_graph_path(graph_id)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"nodes": [], "edges": [], "episodes": [], "metadata": {}}

    def _save_graph(self, graph_id: str, data: Dict):
        path = self._get_graph_path(graph_id)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def add_node(self, graph_id: str, node_id: str, node_data: Dict) -> str:
        with self._get_lock(graph_id):
            graph = self._load_graph(graph_id)
            new_data = {**node_data}
            existing = next((n for n in graph["nodes"] if n["id"] == node_id), None)
            if existing:
                existing.update(new_data)
            else:
                new_data["id"] = node_id
                new_data["created_at"] = time.time()
                graph["nodes"].append(new_data)
            self._save_graph(graph_id, graph)
            return node_id

    def add_edge(self, graph_id: str, source: str, target: str, edge_data: Dict) -> str:
        with self._get_lock(graph_id):
            graph = self._load_graph(graph_id)
            edge_id = f"{source}->{target}"
            existing = next((e for e in graph["edges"] if e.get("id") == edge_id), None)
            if existing:
                existing.update(edge_data)
            else:
                new_data = {**edge_data, "source": source, "target": target,
                            "id": edge_id, "created_at": time.time()}
                graph["edges"].append(new_data)
            self._save_graph(graph_id, graph)
            return edge_id

    def add_episode(self, graph_id: str, episode_data: Dict) -> str:
        with self._get_lock(graph_id):
            graph = self._load_graph(graph_id)
            episode_id = f"ep_{int(time.time() * 1000)}_{len(graph['episodes'])}"
            new_data = {**episode_data, "id": episode_id, "created_at": time.time()}
            graph["episodes"].append(new_data)
            self._save_graph(graph_id, graph)
            return episode_id

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
            "episode_count": len(graph["episodes"]),
            "graph_id": graph_id
        }

    def delete_node(self, graph_id: str, node_id: str) -> bool:
        with self._get_lock(graph_id):
            graph = self._load_graph(graph_id)
            original_count = len(graph["nodes"])
            graph["nodes"] = [n for n in graph["nodes"] if n["id"] != node_id]
            graph["edges"] = [e for e in graph["edges"] if e.get("source") != node_id and e.get("target") != node_id]
            self._save_graph(graph_id, graph)
            return len(graph["nodes"]) < original_count

    def clear_graph(self, graph_id: str):
        with self._get_lock(graph_id):
            self._save_graph(graph_id, {"nodes": [], "edges": [], "episodes": [], "metadata": {}})


local_zep = LocalZepClient()
