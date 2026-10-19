"""Local graph builder - No Zep needed!"""

import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..services.text_processor import TextProcessor
from ..utils.locale import t, get_locale, set_locale
from ..utils.local_storage import get_local_storage


@dataclass
class GraphInfo:
    """Graph info"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class LocalGraphBuilderService:
    """Local graph builder - no Zep API needed!"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.task_manager = TaskManager()
        self.storage = get_local_storage()
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 350
    ) -> str:
        """Build graph asynchronously using local storage"""
        
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        current_locale = get_locale()
        
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, current_locale)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = 'zh'
    ):
        """Graph build worker thread"""
        set_locale(locale)
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Starting local graph build..."
            )
            
            # 1. Create graph
            graph_id = f"local_{uuid.uuid4().hex[:16]}"
            self.storage.add_node(graph_id, graph_id, {
                "type": "graph",
                "name": graph_name,
                "description": "MiroFish Social Simulation Graph",
                "ontology": ontology
            })
            
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Graph created: {graph_id}"
            )
            
            # 2. Process text chunks
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Text split into {total_chunks} chunks"
            )
            
            # 3. Create entities from ontology
            entity_types = ontology.get("entity_types", [])
            edge_types = ontology.get("edge_types", [])
            
            # Create entity type nodes
            for et in entity_types:
                entity_id = f"entity_type_{et.get('name', 'unknown')}"
                self.storage.add_node(graph_id, entity_id, {
                    "type": "entity_type",
                    "name": et.get("name", "Unknown"),
                    "description": et.get("description", ""),
                    "attributes": et.get("attributes", []),
                    "examples": et.get("examples", [])
                })
            
            # Create edge type nodes
            for ed in edge_types:
                edge_id = f"edge_type_{ed.get('name', 'unknown')}"
                self.storage.add_node(graph_id, edge_id, {
                    "type": "edge_type",
                    "name": ed.get("name", "Unknown"),
                    "description": ed.get("description", ""),
                    "source_targets": ed.get("source_targets", [])
                })
            
            # 4. Store text chunks
            for i, chunk in enumerate(chunks):
                chunk_id = f"chunk_{i}"
                self.storage.add_node(graph_id, chunk_id, {
                    "type": "text_chunk",
                    "content": chunk,
                    "index": i
                })
            
            self.task_manager.update_task(
                task_id,
                progress=60,
                message=f"Processed {total_chunks} chunks"
            )

            # 4.5 Extract entity instances with LLM (local full mode)
            extracted = self._extract_entities_from_chunks(
                graph_id, chunks, entity_types, edge_types, task_id
            )

            self.task_manager.update_task(
                task_id,
                progress=75,
                message=f"Extracted {extracted} entities"
            )
            
            # 5. Create relationships
            for edge in edge_types:
                source = edge.get("source_targets", [{}])[0].get("source", "")
                target = edge.get("source_targets", [{}])[0].get("target", "")
                if source and target:
                    self.storage.add_edge(graph_id, 
                        f"entity_type_{source}", 
                        f"entity_type_{target}", 
                        {
                            "type": edge.get("name", "RELATED_TO"),
                            "description": edge.get("description", "")
                        })
            
            self.task_manager.update_task(
                task_id,
                progress=80,
                message="Created relationships"
            )
            
            # 6. Get graph stats
            stats = self.storage.get_graph_stats(graph_id)
            graph_info = GraphInfo(
                graph_id=graph_id,
                node_count=stats["node_count"],
                edge_count=stats["edge_count"],
                entity_types=[et.get("name", "") for et in entity_types]
            )
            
            # Complete
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def _extract_entities_from_chunks(
        self,
        graph_id: str,
        chunks: List[str],
        entity_types: List[Dict[str, Any]],
        edge_types: List[Dict[str, Any]],
        task_id: str,
        max_chunks: int = 50,
    ) -> int:
        """Extract entity instances from text chunks using the configured LLM.

        Returns the number of entity nodes created/updated. Skips silently
        (with a warning) when no LLM key is configured.
        """
        if not Config.LLM_API_KEY:
            import logging
            logging.getLogger("mirofish.local_graph_builder").warning(
                "LLM_API_KEY not set; skipping local entity extraction"
            )
            return 0

        import hashlib
        import re as _re
        from ..utils.llm_client import LLMClient

        type_names = [et.get("name", "") for et in entity_types if et.get("name")]
        edge_names = [ed.get("name", "") for ed in edge_types if ed.get("name")]
        if not type_names:
            return 0

        client = LLMClient()

        system_prompt = (
            "You are an entity extractor. Extract entities and relations from the "
            "text that match the given ontology. Reply ONLY with a JSON object: "
            '{"entities": [{"name": str, "type": str, "summary": str, '
            '"attributes": {str: str}}], '
            '"relations": [{"source": str, "target": str, "type": str, "fact": str}]}. '
            '"type" must be exactly one of the ontology types. '
            'Names must be short canonical identifiers. '
            'If nothing matches, return empty lists.'
        )

        # name(lower) -> node id, for cross-chunk dedup
        entity_name_to_id: Dict[str, str] = {}
        # pre-register any existing entity nodes (resume-safe)
        graph = self.storage._load_graph(graph_id)
        for n in graph.get("nodes", []):
            if n.get("type") == "entity" and n.get("name"):
                entity_name_to_id[n["name"].strip().lower()] = n["id"]

        entities_created = 0
        capped_chunks = chunks[:max_chunks]

        for i, chunk in enumerate(capped_chunks):
            if not chunk or not chunk.strip():
                continue
            user_prompt = (
                f"Ontology entity types: {', '.join(type_names)}\n"
                f"Ontology relation types: {', '.join(edge_names) or 'RELATED_TO'}\n\n"
                f"Text:\n{chunk[:4000]}"
            )
            try:
                result = client.chat_json(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=2048,
                )
            except Exception as e:
                import logging
                logging.getLogger("mirofish.local_graph_builder").warning(
                    f"Entity extraction failed on chunk {i}: {e}"
                )
                continue

            valid_entities = [
                en for en in result.get("entities", [])
                if isinstance(en, dict)
                and en.get("name")
                and en.get("type") in type_names
            ]

            for en in valid_entities:
                name_key = str(en["name"]).strip().lower()
                if not name_key:
                    continue
                node_id = entity_name_to_id.get(name_key)
                if not node_id:
                    slug = _re.sub(r"[^a-zA-Z0-9]+", "_", str(en["name"]).strip())[:40].strip("_")
                    digest = hashlib.md5(name_key.encode("utf-8")).hexdigest()[:8]
                    node_id = f"entity_{slug or 'unnamed'}_{digest}"
                    entity_name_to_id[name_key] = node_id
                    entities_created += 1
                self.storage.add_node(graph_id, node_id, {
                    "type": "entity",
                    "name": str(en["name"]).strip(),
                    "entity_type": en["type"],
                    "labels": ["Entity", en["type"]],
                    "summary": str(en.get("summary") or ""),
                    "attributes": en.get("attributes") or {},
                    "source_chunk": i,
                })

            for rel in result.get("relations", []):
                if not isinstance(rel, dict):
                    continue
                src = entity_name_to_id.get(str(rel.get("source", "")).strip().lower())
                tgt = entity_name_to_id.get(str(rel.get("target", "")).strip().lower())
                if src and tgt and src != tgt:
                    self.storage.add_edge(graph_id, src, tgt, {
                        "type": str(rel.get("type") or "RELATED_TO"),
                        "name": str(rel.get("type") or "RELATED_TO"),
                        "fact": str(rel.get("fact") or ""),
                    })

            if (i + 1) % 10 == 0:
                self.task_manager.update_task(
                    task_id,
                    message=f"Extracting entities: chunk {i + 1}/{len(capped_chunks)}"
                )

        return entities_created

    def validate_batch_chunks(self, chunks, batch_size=350):
        """Validate batch chunks - no-op for local storage"""
        pass

    def delete_graph(self, graph_id: str):
        """Delete a graph"""
        self.storage.clear_graph(graph_id)
