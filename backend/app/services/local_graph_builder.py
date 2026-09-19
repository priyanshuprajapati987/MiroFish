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
    
    def validate_batch_chunks(self, chunks, batch_size=350):
        """Validate batch chunks - no-op for local storage"""
        pass

    def delete_graph(self, graph_id: str):
        """Delete a graph"""
        self.storage.clear_graph(graph_id)
