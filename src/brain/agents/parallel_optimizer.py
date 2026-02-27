"""
Parallel-First Execution Protocol for ATLAS cognitive streamlining.

Reduces cognitive friction by defaulting to parallel tool execution,
eliminating redundant sequential patterns, and optimizing response latency.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    dependencies: list[str] | None = None  # Tools that must complete first
    
class ParallelOptimizer:
    """Optimizes tool execution for minimal cognitive friction."""
    
    def __init__(self, max_parallel: int = 12):  # Increased from 8
        self.max_parallel = max_parallel
        self.execution_stats = {
            'parallel_calls': 0,
            'sequential_calls': 0,
            'time_saved': 0.0
        }
    
    async def execute_optimized(self, tools: list[ToolCall]) -> list[Any]:
        """Execute tools with parallel-first optimization."""
        if not tools:
            return []
            
        # Analyze dependencies and create execution batches
        batches = self._create_execution_batches(tools)
        
        results = []
        for batch in batches:
            if len(batch) == 1:
                # Single tool - execute sequentially
                self.execution_stats['sequential_calls'] += 1
                result = await self._execute_single(batch[0])
                results.append(result)
            else:
                # Multiple tools - execute in parallel
                self.execution_stats['parallel_calls'] += 1
                batch_results = await asyncio.gather(
                    *[self._execute_single(tool) for tool in batch],
                    return_exceptions=True
                )
                results.extend(batch_results)
        
        return results
    
    def _create_execution_batches(self, tools: list[ToolCall]) -> list[list[ToolCall]]:
        """Create execution batches based on dependencies."""
        if not tools:
            return []
            
        # Tools with no dependencies go first
        independent = [t for t in tools if not t.dependencies]
        dependent = [t for t in tools if t.dependencies]
        
        batches = []
        if independent:
            # Batch independent tools up to max_parallel
            batch_size = min(len(independent), self.max_parallel)
            batches.append(independent[:batch_size])
            
            if len(independent) > batch_size:
                # Add remaining independent tools
                batches.append(independent[batch_size:])
        
        # Add dependent tools (they'll execute sequentially)
        if dependent:
            batches.extend([[tool] for tool in dependent])
        
        return batches
    
    async def _execute_single(self, tool: ToolCall) -> Any:
        """Execute a single tool call."""
        # This would integrate with the actual MCP tool execution
        # For now, simulate execution
        await asyncio.sleep(0.1)  # Simulate tool latency
        return f"Result from {tool.name}"
    
    def get_efficiency_report(self) -> dict[str, Any]:
        """Generate efficiency report for entropy manifesto compliance."""
        total_calls = self.execution_stats['parallel_calls'] + self.execution_stats['sequential_calls']
        
        if total_calls == 0:
            return {"efficiency": 1.0, "message": "No tool calls executed"}
        
        parallel_ratio = self.execution_stats['parallel_calls'] / total_calls
        
        return {
            "efficiency": parallel_ratio,
            "parallel_calls": self.execution_stats['parallel_calls'],
            "sequential_calls": self.execution_stats['sequential_calls'],
            "time_saved_estimate": self.execution_stats['time_saved'],
            "entropy_compliance": "HIGH" if parallel_ratio > 0.7 else "NEEDS_IMPROVEMENT"
        }

# Global optimizer instance
parallel_optimizer = ParallelOptimizer()
