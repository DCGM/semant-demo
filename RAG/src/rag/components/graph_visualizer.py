from typing import Optional
from loguru import logger


class GraphVisualizer:  
    def __init__(self, debug_level: int = 0):
        self.debug_level = debug_level
    
    def _visualize_graph(self, workflow_graph, output_format: str = "ascii", output_file: Optional[str] = None) -> str:
        try:
            if output_format.lower() == "ascii":
                if self.debug_level >= 1:
                    logger.info("Generating ASCII graph visualization...")
                
                ascii_graph = workflow_graph.get_graph().draw_ascii()
                
                header = "=" * 80 + "\n"
                header += "RAG Workflow Graph (ASCII)\n"
                header += "=" * 80 + "\n"
                
                result = header + ascii_graph + "\n" + "=" * 80
                
                # save to file if specified
                if output_file:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(result)
                    if self.debug_level >= 1:
                        logger.info(f"ASCII graph saved to: {output_file}")
                
                return result
                
            elif output_format.lower() == "mermaid":
                if self.debug_level >= 1:
                    logger.info("Generating Mermaid PNG graph visualization...")
                
                if not output_file:
                    output_file = "rag_workflow_graph.png"
                
                workflow_graph.get_graph().draw_mermaid_png(output_file)
                
                if self.debug_level >= 1:
                    logger.info(f"Mermaid PNG graph saved to: {output_file}")
                
                return f"Graph visualization saved as PNG: {output_file}"
                
            else:
                raise ValueError(f"Unsupported output format: {output_format}. Use 'ascii' or 'mermaid'")
                
        except Exception as e:
            logger.error(f"Error visualizing graph: {e}")
            return f"Error visualizing graph: {e}"
    
    def get_ascii_graph(self, workflow_graph) -> str:
        return self._visualize_graph(workflow_graph, output_format="ascii")
    
    def get_mermaid_png(self, workflow_graph, output_file: str = "rag_workflow_graph.png") -> str:
        return self._visualize_graph(workflow_graph, output_format="mermaid", output_file=output_file)
