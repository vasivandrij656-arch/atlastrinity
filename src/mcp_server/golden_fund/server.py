import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .lib.storage import SearchStorage, SQLStorage, VectorStorage
from .lib.storage.blob import BlobStorage
from .lib.transformer import DataTransformer
from .tools.chain import recursive_enrichment
from .tools.ingest import ingest_dataset as ingest_impl
from .tools.ingest import search_and_ingest as search_and_ingest_impl

logging.basicConfig(level=logging.INFO, encoding="utf-8")
logger = logging.getLogger("golden_fund")

# Initialize storage
vector_store = VectorStorage()
search_store = SearchStorage()
sql_store = SQLStorage()
transformer = DataTransformer()

# Data directories
CONFIG_ROOT = Path.home() / ".config" / "atlastrinity"
GOLDEN_FUND_DIR = CONFIG_ROOT / "data" / "golden_fund"
ANALYSIS_CACHE_DIR = GOLDEN_FUND_DIR / "analysis_cache"
ANALYSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Create FastMCP server
mcp = FastMCP("golden_fund")


@mcp.tool()
async def search_golden_fund(query: str, mode: str | None = None) -> str:
    """
    Search the Golden Fund knowledge base.

    Args:
        query: The search query.
        mode: Search mode - 'semantic', 'keyword', 'hybrid', or 'recursive'. If None, uses multi-stage fallback.
    """
    logger.info(f"Searching Golden Fund: {query} (mode={mode})")

    if mode == "semantic":
        result = vector_store.search(query)
        return str(result)
    if mode == "keyword":
        result = search_store.search(query)
        return str(result)
    if mode == "hybrid":
        vec_res = vector_store.search(query)
        txt_res = search_store.search(query)
        return f"Hybrid Results:\nVector: {vec_res}\nText: {txt_res}"
    if mode == "recursive":
        return await recursive_enrichment(query)

    # Default: Try keyword first, then semantic, then SQL fallback
    logger.info(f"Attempting multi-stage search for: {query}")
    keyword_res = search_store.search(query)
    if keyword_res.success and keyword_res.data and keyword_res.data.get("results"):
        return str(keyword_res)

    vector_res = vector_store.search(query)
    if vector_res.success and vector_res.data and vector_res.data.get("results"):
        return str(vector_res)

    # SQL Fallback
    logger.info("No results in indexes, attempting SQL fallback...")
    sql_res = _search_sql_fallback(query)
    return str(sql_res)


blob_store = BlobStorage()


@mcp.tool()
async def store_blob(content: str, filename: str | None = None) -> str:
    """Store raw data as a blob (mock MinIO)."""
    return str(blob_store.store(content, filename))


@mcp.tool()
async def retrieve_blob(filename: str) -> str:
    """Retrieve raw data blob."""
    return str(blob_store.retrieve(filename))


@mcp.tool()
async def ingest_dataset(
    url: str,
    type: str,
    process_pipeline: list[str] | None = None,
    offset: int = 0,
    limit: int = 500,
) -> str:
    """
    Ingest a dataset into the Golden Fund.

    Args:
        url: URL of the dataset or API endpoint.
        type: Type of data source (e.g., 'api', 'web_page', 'csv').
        process_pipeline: List of processing steps ('parse', 'store_sql', 'keyword_index', 'vectorize', 'extract_entities').
        offset: Starting record index (for large datasets).
        limit: Max records to index in this step.
    """
    return await ingest_impl(url, type, process_pipeline, offset=offset, limit=limit)


@mcp.tool()
async def search_and_ingest_portals(
    query: str,
    portal_url: str = "https://data.gov.ua/api/3",
    max_datasets: int = 1,
    process_pipeline: list[str] | None = None,
) -> str:
    """
    Search for datasets on a CKAN portal and ingest them.

    Args:
        query: Search query (e.g., 'courts', 'budgets', 'addresses').
        portal_url: CKAN API base URL (default: data.gov.ua).
        max_datasets: Max number of datasets to try ingesting.
        process_pipeline: List of steps ('parse', 'store_sql', 'keyword_index', 'vectorize', 'extract_entities').
    """
    return await search_and_ingest_impl(query, portal_url, max_datasets, process_pipeline)


@mcp.tool()
async def probe_entity(entity_id: str, depth: int = 1) -> str:
    """Probe the knowledge graph for an entity to explore relationships."""
    logger.info(f"Probing entity: {entity_id} (depth={depth})")

    # Search for the entity
    results = _find_entity_results(entity_id)

    if not results:
        return json.dumps(
            {
                "entity_id": entity_id,
                "found": False,
                "message": "Entity not found in Golden Fund. Consider ingesting relevant data first.",
                "suggestion": f"Use ingest_dataset or add_knowledge_node to add information about '{entity_id}'",
            }
        )

    # Build entity profile from results
    entity_profile = _build_entity_profile(entity_id, results, depth)

    # Recursive depth exploration
    if depth > 1 and entity_profile["related_entities"]:
        _explore_deeper(entity_profile)

    return json.dumps(entity_profile, indent=2, default=str)


def _find_entity_results(entity_id: str) -> list[dict[str, Any]]:
    """Helper to find entity matches using keyword, vector, and SQL fallback."""
    # Try keyword first (exact matches)
    keyword_result = search_store.search(entity_id)
    results = (
        keyword_result.data.get("results", [])
        if keyword_result.success and keyword_result.data
        else []
    )

    if not results:
        # Try vector search
        search_result = vector_store.search(entity_id, limit=5)
        results = (
            search_result.data.get("results", [])
            if search_result.success and search_result.data
            else []
        )

    if not results:
        # Try SQL fallback
        sql_res = _search_sql_fallback(entity_id)
        if sql_res:
            results = [{"content": r, "score": 0.5, "metadata": r} for r in sql_res]

    return results


def _search_sql_fallback(query: str) -> list[dict[str, Any]]:
    """Search for relevant tables and query them directly."""
    try:
        # 1. Find datasets that might contain the query in their metadata
        meta_query = "SELECT table_name FROM datasets_metadata WHERE dataset_name LIKE ? OR source_url LIKE ?"
        meta_res = sql_store.query(meta_query, (f"%{query}%", f"%{query}%"))

        tables = []
        if meta_res.success and meta_res.data:
            tables = [r["table_name"] for r in meta_res.data]

        # 2. Also just look for the last 3 ingested tables as a broad search
        recent_res = sql_store.query(
            "SELECT table_name FROM datasets_metadata ORDER BY ingested_at DESC LIMIT 3"
        )
        if recent_res.success and recent_res.data:
            tables.extend([r["table_name"] for r in recent_res.data])

        tables = list(set(tables))
        all_results = []

        for table in tables:
            # Query the table for matching content (broad search across all columns)
            # Find columns first
            cols_res = sql_store.query(f"PRAGMA table_info({table})")
            if not cols_res.success or not cols_res.data:
                continue

            text_cols = [
                r["name"]
                for r in cols_res.data
                if "TEXT" in str(r["type"]).upper() or "CHAR" in str(r["type"]).upper()
            ]
            if not text_cols:
                continue

            where_clause = " OR ".join([f"{col} LIKE ?" for col in text_cols])
            search_query = f"SELECT * FROM {table} WHERE {where_clause} LIMIT 5"
            data_res = sql_store.query(search_query, tuple([f"%{query}%"] * len(text_cols)))

            if data_res.success and data_res.data:
                for r in data_res.data:
                    r["_source_table"] = table
                    all_results.append(r)

        return all_results
    except Exception as e:
        logger.error(f"SQL fallback search failed: {e}")
        return []


def _build_entity_profile(
    entity_id: str, results: list[dict[str, Any]], depth: int
) -> dict[str, Any]:
    """Helper to build an entity profile from search results."""
    entity_profile: dict[str, Any] = {
        "entity_id": entity_id,
        "found": True,
        "depth": depth,
        "matches": [],
        "related_entities": [],
        "metadata": {},
    }

    seen_entities = {entity_id}

    for result in results[:10]:  # Limit to top 10
        match_info = {
            "id": result.get("id"),
            "score": round(result.get("score", 0), 4),
            "content_preview": str(result.get("content", ""))[:200],
        }

        # Extract metadata and relationships
        meta = result.get("metadata", {})
        if meta:
            match_info["metadata"] = meta
            _extract_relationships(entity_profile, meta, seen_entities)

        entity_profile["matches"].append(match_info)
    return entity_profile


def _extract_relationships(
    entity_profile: dict[str, Any], meta: dict[str, Any], seen_entities: set[str]
) -> None:
    """Extract related entities from metadata and add to profile."""
    for key, value in meta.items():
        if isinstance(value, str) and len(value) > 2 and key not in ["timestamp", "source_format"]:
            if value not in seen_entities:
                seen_entities.add(value)
                entity_profile["related_entities"].append(
                    {
                        "name": value,
                        "relation": key,
                    }
                )


def _explore_deeper(entity_profile: dict[str, Any]) -> None:
    """Perform deeper recursive depth exploration."""
    entity_profile["deeper_exploration"] = []
    # Limit recursion to top 3 related entities
    for related in entity_profile["related_entities"][:3]:
        sub_result = vector_store.search(related["name"], limit=2)
        if sub_result.success and sub_result.data:
            sub_matches = sub_result.data.get("results", [])
            if sub_matches:
                entity_profile["deeper_exploration"].append(
                    {
                        "entity": related["name"],
                        "relation": related["relation"],
                        "sub_matches_count": len(sub_matches),
                    }
                )


@mcp.tool()
async def add_knowledge_node(
    content: str, metadata: dict[str, Any], links: list[dict[str, str]] | None = None
) -> str:
    """
    Manually add a confirmed knowledge node to the Golden Fund.

    Args:
        content: The core information/text of the node.
        metadata: Key-value metadata pairs (e.g., {'type': 'company', 'source': 'manual'}).
        links: List of links to other nodes [{'relation': 'related_to', 'target_id': '...'}]
    """
    if links is None:
        links = []

    logger.info(f"Adding knowledge node: {content[:50]}...")

    # Transform to unified schema
    node_data = {
        "name": metadata.get("name", content[:50]),
        "type": metadata.get("type", "entity"),
        "content": content,
        **metadata,
    }

    transform_result = transformer.transform(node_data, source_format="manual")

    if not transform_result.success:
        return json.dumps({"success": False, "error": transform_result.error})

    # Store in vector DB
    if transform_result.data is None:
        return json.dumps({"success": False, "error": "Transformation produced no data"})

    store_result = vector_store.store(transform_result.data)

    if not store_result.success:
        return json.dumps({"success": False, "error": store_result.error})

    # Process links (create relationships)
    links_created = 0
    for link in links:
        target_id = link.get("target_id")
        relation = link.get("relation", "related_to")
        if target_id:
            # Store link as a separate node for now (simplified approach)
            link_node = {
                "name": f"link_{node_data['name']}_{target_id}",
                "type": "relationship",
                "source": node_data["name"],
                "target": target_id,
                "relation": relation,
            }
            vector_store.store(link_node)
            links_created += 1

    return json.dumps(
        {
            "success": True,
            "node_id": store_result.data.get("records_inserted", 1) if store_result.data else 1,
            "links_created": links_created,
            "message": f"Knowledge node '{node_data['name']}' added to Golden Fund",
        }
    )


@mcp.tool()
async def analyze_and_store(
    file_path: str,
    dataset_name: str,
    analysis_type: str = "summary",
) -> str:
    """
    Analyze a data file and store insights in Golden Fund.
    Bridges data-analysis capabilities with knowledge persistence.

    Args:
        file_path: Path to CSV, Excel, or JSON file.
        dataset_name: Name for this dataset in the knowledge base.
        analysis_type: Type of analysis - 'summary', 'correlation', 'distribution'.
    """
    import pandas as pd

    logger.info(f"Analyzing and storing: {file_path} as '{dataset_name}'")

    path = Path(file_path).expanduser()
    if not path.exists():
        return json.dumps({"success": False, "error": f"File not found: {file_path}"})

    try:
        # Load data
        suffix = path.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(path, nrows=10000)
        elif suffix in [".xlsx", ".xls"]:
            df = pd.read_excel(path, nrows=10000)
        elif suffix == ".json":
            df = pd.read_json(path)
        else:
            return json.dumps({"success": False, "error": f"Unsupported format: {suffix}"})

        # Generate analysis
        analysis: dict[str, Any] = {
            "dataset_name": dataset_name,
            "file_path": str(path),
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "analysis_type": analysis_type,
            "timestamp": datetime.now().isoformat(),
        }

        # Add statistics based on analysis type
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

        if analysis_type == "summary":
            if numeric_cols:
                analysis["numeric_summary"] = df[numeric_cols].describe().to_dict()
            analysis["missing_values"] = df.isna().sum().to_dict()

        elif analysis_type == "correlation":
            if len(numeric_cols) > 1:
                # Cast df[numeric_cols] to Any to avoid Series/float inference confusion
                df_numeric: Any = df[numeric_cols]
                corr: Any = df_numeric.corr()
                # Find strong correlations
                strong = []
                for i in range(len(corr.columns)):
                    for j in range(i + 1, len(corr.columns)):
                        val = corr.iloc[i, j]
                        # Handle potential Timedelta or other non-float types from pandas corr
                        try:
                            # Cast val to Any to satisfy Pyrefly's strict type checking
                            v_any: Any = val
                            f_val = float(v_any)
                            if abs(f_val) > 0.7:
                                strong.append(
                                    {
                                        "col1": str(corr.columns[i]),
                                        "col2": str(corr.columns[j]),
                                        "correlation": round(f_val, 4),
                                    }
                                )
                        except (TypeError, ValueError):
                            continue
                analysis["strong_correlations"] = strong

        elif analysis_type == "distribution":
            analysis["distributions"] = {}
            for col in numeric_cols[:5]:
                series = df[col].dropna()
                if len(series) > 0:
                    series_any: Any = series
                    dist_meta: dict[str, Any] = {
                        "mean": round(float(series_any.mean()), 4),
                        "median": float(series_any.median()),
                        "std": round(float(series_any.std()), 4),
                    }

                    analysis["distributions"][col] = dist_meta

        # Store in Golden Fund
        store_result = vector_store.store(analysis)

        # Save analysis to cache
        cache_file = (
            ANALYSIS_CACHE_DIR / f"{dataset_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, default=str)

        return json.dumps(
            {
                "success": True,
                "dataset_name": dataset_name,
                "rows_analyzed": len(df),
                "columns": len(df.columns),
                "stored_in_golden_fund": store_result.success,
                "cache_file": str(cache_file),
                "message": f"Dataset '{dataset_name}' analyzed and stored in Golden Fund",
            }
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def get_dataset_insights(dataset_name: str) -> str:
    """
    Retrieve stored insights for a dataset from Golden Fund.

    Args:
        dataset_name: Name of the dataset to retrieve insights for.
    """
    logger.info(f"Retrieving insights for: {dataset_name}")

    # Search for dataset in vector store
    result = vector_store.search(dataset_name, limit=5)

    if not result.success:
        return json.dumps({"success": False, "error": result.error})

    matches = result.data.get("results", []) if result.data else []

    if not matches:
        return json.dumps(
            {
                "success": False,
                "dataset_name": dataset_name,
                "message": "No insights found. Use analyze_and_store to analyze the dataset first.",
            }
        )

    # Filter for dataset-type matches
    insights = []
    for match in matches:
        content = match.get("content", "")
        try:
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = content
            if (
                data.get("dataset_name") == dataset_name
                or dataset_name.lower() in str(data).lower()
            ):
                insights.append({"score": round(match.get("score", 0), 4), "data": data})
        except (json.JSONDecodeError, TypeError):
            pass

    return json.dumps(
        {
            "success": True,
            "dataset_name": dataset_name,
            "insights_count": len(insights),
            "insights": insights[:5],  # Top 5
        },
        indent=2,
        default=str,
    )


if __name__ == "__main__":
    mcp.run()
