"""
Ingestion Tool for Golden Fund
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..lib.entity_extractor import EntityExtractor
from ..lib.parser import DataParser
from ..lib.scraper import DataScraper
from ..lib.storage import SearchStorage, SQLStorage, VectorStorage
from ..lib.validation import DataValidator

from ..lib.connectors.ckan_connector import CKANConnector

logger = logging.getLogger("golden_fund.tools.ingest")

# Define storage path (Global config directory)
CONFIG_ROOT = Path.home() / ".config" / "atlastrinity"
DATA_DIR = CONFIG_ROOT / "data" / "golden_fund"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)


async def search_and_ingest(
    query: str,
    portal_url: str = "https://data.gov.ua/api/3",
    max_datasets: int = 1,
    process_pipeline: list[str] | None = None,
) -> str:
    """
    Search for datasets on a CKAN portal and ingest the most relevant ones.

    Args:
        query: Search query for the portal.
        portal_url: Base URL of the CKAN API.
        max_datasets: Maximum number of datasets to ingest.
        process_pipeline: List of processing steps.
    """
    connector = CKANConnector(portal_url)
    packages = connector.search_packages(query, rows=max_datasets)

    if not packages:
        return f"No datasets found for query '{query}' on {portal_url}"

    results = []
    for pkg in packages:
        pkg_id = pkg.get("name") or pkg.get("id")
        title = pkg.get("title", pkg_id)
        logger.info(f"Processing discovered package: {title}")

        # Find suitable resources (CSV, JSON, etc.)
        resources = connector.find_resources_by_format(pkg, formats=["CSV", "JSON", "XLSX", "XML"])
        if not resources:
            results.append(f"Package '{title}': No supported resources found.")
            continue

        # Ingest the first suitable resource
        res = resources[0]
        res_url = connector.get_resource_url(res)
        res_format = res.get("format", "").lower()

        logger.info(f"Ingesting resource: {res_url} ({res_format})")
        ingest_res = await ingest_dataset(
            url=res_url,
            type=res_format,
            process_pipeline=process_pipeline,
        )
        results.append(f"Package '{title}': {ingest_res}")

    return "\n".join(results)


def _get_scrape_result(url: str, type: str, scraper: DataScraper):
    """Helper to handle the first stage of ingestion: scraping."""
    if type == "api":
        return scraper.scrape_api_endpoint(url), ".json"
    if type == "web_page":
        return scraper.scrape_web_page(url), ".json"

    # Generic file download
    result = scraper.download_file(url)
    if type in ["csv", "json", "xml", "parquet"]:
        ext = f".{type}"
    elif type in ["excel", "xlsx", "xls"]:
        ext = ".xlsx"
    else:
        path = Path(url)
        ext = path.suffix or ".bin"
    return result, ext


def _parse_raw_data(raw_file: Path, ext: str, type: str, parser: DataParser):
    """Helper to handle the second stage: parsing."""
    format_hint = ext.lstrip(".").lower()
    if format_hint == "bin" and type not in ["file", "web_page", "api"]:
        format_hint = type

    return parser.parse(raw_file, format_hint=format_hint)


async def ingest_dataset(
    url: str,
    type: str = "web_page",
    process_pipeline: list[str] | None = None,
    offset: int = 0,
    limit: int = 500,
) -> str:
    """
    Ingest a dataset from a URL.

    Args:
        url: Source URL.
        type: Source type (api, web_page, csv, etc).
        process_pipeline: Processing stages.
        offset: Starting record index.
        limit: Number of records to process in this step.
    """
    scraper = DataScraper()
    parser = DataParser()
    validator = DataValidator()
    sql_storage = SQLStorage()
    vector_storage = VectorStorage()
    search_storage = SearchStorage()
    entity_extractor = EntityExtractor()

    if process_pipeline is None:
        process_pipeline = ["parse", "store_sql", "keyword_index", "vectorize", "extract_entities"]

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    logger.info(f"Starting ingestion run {run_id} for {url} ({type})")

    result, ext = _get_scrape_result(url, type, scraper)
    if not result.success:
        msg = f"Ingestion failed during retrieval: {result.error}"
        logger.error(msg)
        return msg

    if not result.data:
        return "No data retrieved"

    # Fix: Handle BeautifulSoup object from scrape_web_page
    data_to_save = result.data
    text_content_for_extraction = ""

    if type == "web_page" and hasattr(data_to_save, "get_text"):
        text_content_for_extraction = data_to_save.get_text(separator="\n", strip=True)
        title_obj = getattr(data_to_save, "title", None)
        title_str = title_obj.string if title_obj else ""

        data_to_save = {
            "title": title_str,
            "text": text_content_for_extraction,
            "html": str(data_to_save),
        }
    elif isinstance(data_to_save, str):
        text_content_for_extraction = data_to_save
    elif isinstance(data_to_save, dict):
        text_content_for_extraction = str(data_to_save)

    raw_file = RAW_DIR / f"{run_id}_raw{ext}"
    save_res = scraper.save_data(data_to_save, raw_file)
    if not save_res.success:
        return f"Failed to save raw data: {save_res.error}"

    summary_parts = [f"Ingestion {run_id} successful.", f"Raw data: {raw_file.name}."]
    parsed_df = None

    if "parse" in process_pipeline:
        parsed_df, parse_msg = _perform_parsing(raw_file, ext, type, parser)
        summary_parts.append(parse_msg)

    if parsed_df is not None:
        total_records = len(parsed_df)
        # Applying offset/limit slicing
        chunk_df = parsed_df.iloc[offset : offset + limit]
        actual_limit = len(chunk_df)
        summary_parts.append(
            f"Processing chunk: records {offset} to {offset + actual_limit} of {total_records}."
        )

        if "store_sql" in process_pipeline and offset == 0:
            # Only store in SQL once (from the first chunk call or full parse)
            # Note: We store the ENTIRE parsed_df in SQL for structured queries
            sql_msg = _perform_sql_storage(parsed_df, run_id, url, sql_storage)
            summary_parts.append(sql_msg)

        if "vectorize" in process_pipeline:
            # Vectorize the sliced chunk
            vec_msg = _perform_vector_storage(
                chunk_df, run_id, url, ext, vector_storage, offset=offset
            )
            summary_parts.append(vec_msg)

        if "keyword_index" in process_pipeline:
            # Keyword index the sliced chunk
            search_msg = _perform_keyword_storage(chunk_df, run_id, search_storage, offset=offset)
            summary_parts.append(search_msg)

        if "validate" in process_pipeline:
            val_msg = _perform_validation(chunk_df, run_id, validator)
            summary_parts.append(val_msg)

        if "extract_entities" in process_pipeline and offset == 0:
            # Entity extraction usually summarizes the whole doc, or first 50 rows
            # We skip it for continuation chunks to save time
            if not text_content_for_extraction:
                sample_df = parsed_df.head(50)
                text_content_for_extraction = sample_df.to_json(orient="records", force_ascii=False)

            if text_content_for_extraction:
                ent_msg = _perform_entity_storage(
                    text_content_for_extraction, url, run_id, entity_extractor, vector_storage
                )
                summary_parts.append(ent_msg)

        # Continuation Protocol
        if offset + actual_limit < total_records:
            next_offset = offset + actual_limit
            summary_parts.append(
                f"\n[CONTINUATION REQUIRED] Dataset has {total_records} records. "
                f"To continue, call: ingest_dataset(url='{url}', type='{type}', offset={next_offset}, limit={limit})"
            )

    return " ".join(summary_parts)


def _perform_parsing(
    raw_file: Path, ext: str, type: str, parser: DataParser
) -> tuple[pd.DataFrame | None, str]:
    """Helper to parse raw data into a DataFrame."""
    parse_res = _parse_raw_data(raw_file, ext, type, parser)
    if not parse_res.success:
        return None, f"Parsing failed: {parse_res.error}"

    data = parse_res.data
    df = None
    if isinstance(data, pd.DataFrame):
        df = data
    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        df = pd.DataFrame(data)
    elif isinstance(data, dict):
        df = pd.DataFrame([data])

    count = len(df) if df is not None else 0
    return df, f"Parsed {count} records."


def _perform_sql_storage(df: pd.DataFrame, run_id: str, url: str, sql_storage: SQLStorage) -> str:
    """Helper to store dataset in SQL database."""
    table_name = f"dataset_{run_id}"
    store_res = sql_storage.store_dataset(df, table_name, source_url=url)
    if store_res.success:
        return f"Stored in SQL table '{store_res.target}'."
    return f"SQL Storage failed: {store_res.error}"


def _perform_vector_storage(
    df: pd.DataFrame,
    run_id: str,
    url: str,
    ext: str,
    vector_storage: VectorStorage,
    offset: int = 0,
) -> str:
    """Helper to store dataset metadata and sliced records in vector database."""
    cols = ", ".join(df.columns[:10])
    desc = f"Dataset from {url} ({ext}). Columns: {cols}. Rows: {len(df)}."
    table_name = f"dataset_{run_id}"

    vector_data = [
        {
            "name": table_name,
            "type": "dataset_metadata",
            "content": desc,
            "source_url": url,
            "format": ext,
            "sql_table": table_name,
        }
    ]

    # Vectorize individual records in this chunk
    for i, row in df.iterrows():
        global_index = offset + i if isinstance(i, int) else i  # Handle non-integer index if any
        row_dict = row.to_dict()
        row_text = " | ".join([f"{k}: {v}" for k, v in row_dict.items() if pd.notna(v)])

        # Prepare metadata (only simple types for ChromaDB)
        meta = {str(k): v for k, v in row_dict.items() if isinstance(v, str | int | float | bool)}
        meta["source_url"] = url
        meta["format"] = ext
        meta["sql_table"] = table_name

        record_data: dict[str, Any] = {
            "name": f"{table_name}_record_{global_index}",
            "type": "dataset_record",
            "content": row_text,
            "source_url": url,
            "format": ext,
            "sql_table": table_name,
        }
        # Add the meta fields
        record_data.update(meta)
        vector_data.append(record_data)

    vec_res = vector_storage.store(vector_data)
    if vec_res.success:
        return f"Indexed {len(df)} records for semantic search."
    return f"Vector indexing failed: {vec_res.error}"


def _perform_validation(df: pd.DataFrame, run_id: str, validator: DataValidator) -> str:
    """Helper to validate ingested data completeness."""
    val_data = [{str(k): v for k, v in record.items()} for record in df.to_dict(orient="records")]
    validation_res = validator.validate_data_completeness(val_data, context=f"ingestion_{run_id}")
    if validation_res.success:
        return "Validation passed."
    return f"Validation warning: {validation_res.error}"


def _perform_keyword_storage(
    df: pd.DataFrame, run_id: str, search_storage: SearchStorage, offset: int = 0
) -> str:
    """Helper to index a slice of rows for keyword search."""
    records = df.to_dict(orient="records")
    # Add some descriptive fields for FTS5
    indexed_records: list[dict[str, Any]] = []
    for i, rec in enumerate(records):
        global_index = offset + i
        str_rec = {str(k): v for k, v in rec.items()}
        indexed_records.append(
            {
                "id": f"{run_id}_{global_index}",
                "title": str(str_rec.get("name") or str_rec.get("title") or f"Record {i}"),
                "content": " ".join([f"{k}:{v}" for k, v in str_rec.items()]),
                "description": f"Part of dataset {run_id}",
                **str_rec,
            }
        )

    res = search_storage.index_documents(indexed_records)
    if res.success:
        return f"Indexed {len(records)} records for keyword search."
    return f"Keyword indexing failed: {res.error}"


def _perform_entity_storage(
    text: str,
    source_url: str,
    run_id: str,
    extractor: EntityExtractor,
    vector_storage: VectorStorage,
) -> str:
    """Helper to extract and store entities and relationships."""
    logger.info(f"Extracting entities from {len(text)} chars...")
    extraction = extractor.extract(text, source_url)
    entities = extraction.get("entities", [])
    relationships = extraction.get("relationships", [])

    count_ent = 0
    for ent in entities:
        vector_storage.store(
            {
                "name": ent.get("name"),
                "type": "entity",
                "entity_type": ent.get("type"),
                "content": ent.get("description", ""),
                "source_url": source_url,
                "run_id": run_id,
            }
        )
        count_ent += 1

    count_rel = 0
    for rel in relationships:
        vector_storage.store(
            {
                "name": f"{rel.get('source')} -> {rel.get('target')}",
                "type": "relationship",
                "relation": rel.get("relation"),
                "source_entity": rel.get("source"),
                "target_entity": rel.get("target"),
                "content": f"{rel.get('source')} {rel.get('relation')} {rel.get('target')}",
                "source_url": source_url,
                "run_id": run_id,
            }
        )
        count_rel += 1

    return f"Extracted {count_ent} entities and {count_rel} relationships."
