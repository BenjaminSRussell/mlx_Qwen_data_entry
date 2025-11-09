"""Prompt builder for Qwen Architect."""

from typing import List, Dict, Any
from datetime import datetime

from ..common.models import WorkloadSnapshot, EvalResult


class PromptBuilder:
    """Builds prompts for the Qwen Architect."""

    def __init__(
        self,
        include_schema: bool = True,
        include_workload_stats: bool = True,
        include_current_config: bool = True,
        max_workload_entries: int = 50
    ):
        """
        Initialize prompt builder.

        Args:
            include_schema: Include database schema in prompt
            include_workload_stats: Include workload statistics
            include_current_config: Include current configuration
            max_workload_entries: Maximum workload entries to include
        """
        self.include_schema = include_schema
        self.include_workload_stats = include_workload_stats
        self.include_current_config = include_current_config
        self.max_workload_entries = max_workload_entries

    def build_system_prompt(self) -> str:
        """Build system prompt for the Architect."""
        return """You are an expert Database Administrator AI assistant specializing in PostgreSQL and vector database optimization.

Your role is to analyze workload data, identify performance bottlenecks, and recommend specific, actionable optimizations.

You should output recommendations in the following JSON format:

{
  "recommendation_id": "unique-id",
  "recommendation_type": "index|query_rewrite|schema_change|config_tuning|vector_params",
  "priority": "critical|high|medium|low",
  "title": "Brief title of the recommendation",
  "rationale": "Detailed explanation of why this recommendation is needed",
  "config_patch": {
    "type": "specific change type",
    "details": {
      // Specific configuration changes
    }
  },
  "expected_effects": {
    "latency_improvement_percent": 25.0,
    "cost_reduction_percent": 10.0,
    "affected_queries": ["query_fingerprint_1", "query_fingerprint_2"]
  },
  "risk_level": "low|medium|high",
  "risk_notes": "Explanation of risks",
  "migration_sql": "-- SQL to apply the change",
  "rollback_sql": "-- SQL to rollback the change",
  "confidence_score": 0.85
}

Focus on:
1. High-impact queries (high frequency × high latency)
2. Missing indexes
3. Inefficient query patterns
4. Suboptimal configuration parameters
5. Vector search optimization opportunities

Be specific and provide actionable SQL or configuration changes."""

    def build_workload_summary(
        self,
        snapshots: List[WorkloadSnapshot]
    ) -> str:
        """Build workload summary section."""
        if not snapshots:
            return "No workload data available."

        # Limit to top N by impact
        top_snapshots = sorted(
            snapshots,
            key=lambda s: s.impact_score,
            reverse=True
        )[:self.max_workload_entries]

        summary = "## Workload Summary\n\n"
        summary += f"Total query patterns analyzed: {len(snapshots)}\n"
        summary += f"Showing top {len(top_snapshots)} by impact score:\n\n"

        for i, snapshot in enumerate(top_snapshots, 1):
            summary += f"### Query Pattern {i}\n"
            summary += f"- Fingerprint: `{snapshot.query_fingerprint[:100]}...`\n"
            summary += f"- Type: {snapshot.query_type}\n"
            summary += f"- Source: {snapshot.query_source}\n"
            summary += f"- Executions: {snapshot.execution_count:,}\n"
            summary += f"- P95 Latency: {snapshot.p95_latency_ms:.2f}ms\n"
            summary += f"- P99 Latency: {snapshot.p99_latency_ms:.2f}ms\n"
            summary += f"- Impact Score: {snapshot.impact_score:,.0f}\n"

            if snapshot.avg_rows_returned:
                summary += f"- Avg Rows Returned: {snapshot.avg_rows_returned:.0f}\n"
            if snapshot.avg_rows_scanned:
                summary += f"- Avg Rows Scanned: {snapshot.avg_rows_scanned:.0f}\n"

            if snapshot.error_rate > 0:
                summary += f"- Error Rate: {snapshot.error_rate:.2%}\n"

            summary += f"- Example Query: `{snapshot.example_query[:200]}...`\n\n"

        return summary

    def build_eval_summary(
        self,
        eval_results: List[EvalResult]
    ) -> str:
        """Build evaluation results summary."""
        if not eval_results:
            return "No evaluation results available."

        summary = "## Evaluation Results\n\n"

        for result in eval_results:
            summary += f"### {result.eval_type}\n"
            summary += f"- Timestamp: {result.eval_timestamp}\n"

            if result.overall_score:
                summary += f"- Overall Score: {result.overall_score:.4f}\n"

            if result.p95_latency_ms:
                summary += f"- P95 Latency: {result.p95_latency_ms:.2f}ms\n"

            if result.p99_latency_ms:
                summary += f"- P99 Latency: {result.p99_latency_ms:.2f}ms\n"

            if result.rag_mrr:
                summary += f"- RAG MRR: {result.rag_mrr:.4f}\n"

            if result.slo_passed is not None:
                summary += f"- SLO Status: {'PASSED' if result.slo_passed else 'FAILED'}\n"

            if result.slo_violations:
                summary += f"- SLO Violations: {list(result.slo_violations.keys())}\n"

            summary += "\n"

        return summary

    def build_schema_summary(self, schema_info: Dict[str, Any] = None) -> str:
        """Build database schema summary."""
        if not self.include_schema or not schema_info:
            return "## Database Schema\n\n(Schema information not provided)\n\n"

        summary = "## Database Schema\n\n"

        if 'tables' in schema_info:
            summary += "### Tables\n"
            for table in schema_info['tables']:
                summary += f"- {table['name']}\n"
                if 'columns' in table:
                    for col in table['columns'][:5]:  # Limit columns
                        summary += f"  - {col['name']}: {col['type']}\n"
            summary += "\n"

        if 'indexes' in schema_info:
            summary += "### Existing Indexes\n"
            for idx in schema_info['indexes'][:20]:  # Limit indexes
                summary += f"- {idx['name']} on {idx['table']}\n"
            summary += "\n"

        return summary

    def build_config_summary(self, config: Dict[str, Any] = None) -> str:
        """Build current configuration summary."""
        if not self.include_current_config or not config:
            return "## Current Configuration\n\n(Configuration information not provided)\n\n"

        summary = "## Current Configuration\n\n"
        summary += "```yaml\n"

        for key, value in config.items():
            summary += f"{key}: {value}\n"

        summary += "```\n\n"

        return summary

    def build_analysis_prompt(
        self,
        workload_snapshots: List[WorkloadSnapshot],
        eval_results: List[EvalResult] = None,
        schema_info: Dict[str, Any] = None,
        current_config: Dict[str, Any] = None,
        focus_areas: List[str] = None
    ) -> str:
        """
        Build complete analysis prompt.

        Args:
            workload_snapshots: Recent workload snapshots
            eval_results: Recent evaluation results
            schema_info: Database schema information
            current_config: Current system configuration
            focus_areas: Areas to focus on

        Returns:
            Complete prompt for the Architect
        """
        prompt = "# Database Performance Analysis Request\n\n"
        prompt += f"Date: {datetime.utcnow().isoformat()}\n\n"

        # Add workload summary
        if self.include_workload_stats:
            prompt += self.build_workload_summary(workload_snapshots)

        # Add evaluation results
        if eval_results:
            prompt += self.build_eval_summary(eval_results)

        # Add schema information
        if schema_info:
            prompt += self.build_schema_summary(schema_info)

        # Add current configuration
        if current_config:
            prompt += self.build_config_summary(current_config)

        # Add focus areas
        if focus_areas:
            prompt += "## Focus Areas\n\n"
            for area in focus_areas:
                prompt += f"- {area}\n"
            prompt += "\n"

        # Request
        prompt += """## Task

Analyze the workload data and evaluation results above. Identify the single most impactful optimization opportunity.

Provide ONE recommendation in the JSON format specified in your system prompt.

Focus on changes that will have the highest impact on performance with acceptable risk.

Return ONLY the JSON object, no additional text."""

        return prompt
