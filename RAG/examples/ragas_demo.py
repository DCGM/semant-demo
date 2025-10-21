import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

from rag.main import Agentic_RAG_app
from rag.evaluation.ragas_evaluator import SimpleRAGASEvaluator


async def main():
    app = Agentic_RAG_app(debug_level=1)
    evaluator = SimpleRAGASEvaluator(vectorstore=app.vectorstore)
    
    evaluation_data = [
        {
            "query": "What is the history of mathematics?",
            "ground_truth": "Mathematics has a rich history dating back to ancient civilizations. The ancient Egyptians and Babylonians developed early mathematical concepts, while the Greeks, particularly Pythagoras and Euclid, established formal mathematical foundations."
        },
        # {
        #     "query": "Explain the basic principles of physics",
        #     "ground_truth": "Physics is the study of matter, energy, and their interactions. Basic principles include Newton's laws of motion, which describe how objects move and respond to forces. The law of conservation of energy states that energy cannot be created or destroyed, only transformed."
        # }
    ]
    
    results = await evaluator.evaluate_batch(evaluation_data)
    
    for i, result in enumerate(results):
        print(f"\nQuery {i+1}:")
        for key, value in result.items():
            if isinstance(value, (int, float)):
                print(f"{key}: {value:.3f}")
            elif isinstance(value, list):
                print(f"{key}: {len(value)} items")
                for j, item in enumerate(value[:2]):  # Show first 2 items
                    print(f"  [{j}]: {item[:100]}...")  # Truncate long text
            else:
                print(f"{key}: {value}")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())
