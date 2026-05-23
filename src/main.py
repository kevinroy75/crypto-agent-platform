"""
Main entry point for the multi-agent crypto research platform.
"""
import asyncio
import argparse
import json
from pathlib import Path

from src.agents.orchestrator import OrchestratorAgent


async def run(task: str, verbose: bool = False):
    """Run a research task through the multi-agent system."""
    orchestrator = OrchestratorAgent(verbose=verbose)
    result = await orchestrator.execute(task)
    
    if verbose:
        print("\n" + "=" * 60)
        print("FINAL RESULT")
        print("=" * 60)
    
    print(result.output)
    
    if result.artifacts:
        print(f"\nArtifacts generated: {len(result.artifacts)}")
        for artifact in result.artifacts:
            print(f"  - {artifact}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Crypto Research Platform")
    parser.add_argument("--task", type=str, required=True, help="Research task to execute")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--config", type=str, default="configs/agents.yaml", help="Config file path")
    parser.add_argument("--output", type=str, help="Output file path for results")
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="text", help="Output format")
    
    args = parser.parse_args()
    
    result = asyncio.run(run(args.task, args.verbose))
    
    if args.output:
        output_path = Path(args.output)
        if args.format == "json":
            output_path.write_text(json.dumps(result.to_dict(), indent=2))
        elif args.format == "markdown":
            output_path.write_text(result.to_markdown())
        else:
            output_path.write_text(result.output)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
