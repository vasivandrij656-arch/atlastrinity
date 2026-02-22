"""
Data Scraper Module for Golden Fund

Provides functionality to scrape data from open data portals and save it.
Ported from etl_module/src/scraping/data_scraper.py
"""

import csv
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.mcp_server.tool_result_interface import ToolResult

# Initialize logger
logger = logging.getLogger("golden_fund.scraper")


class ScrapeFormat(Enum):
    """Supported output formats for scraped data."""

    CSV = "csv"
    JSON = "json"
    XML = "xml"


class ScrapeResult(ToolResult):
    """Result container for scraping operations."""

    def __init__(self, success: bool, data: Any | None = None, error: str | None = None):
        self._success = success
        self._data = data
        self._error = error
        self.timestamp = datetime.now()
        self.metadata: dict[str, Any] = {}

    @property
    def success(self) -> bool:
        return self._success

    @property
    def data(self) -> Any:
        return self._data

    @property
    def error(self) -> str | None:
        return self._error

    def __repr__(self) -> str:
        if self.success:
            return f"ScrapeResult(success=True, records={len(self.data) if isinstance(self.data, list) else 1})"
        return f"ScrapeResult(success=False, error={self.error})"


class DataScraper:
    """
    Data scraper for open data portals.
    """

    def __init__(self, user_agent: str = "AtlasTrinity-GoldenFund/1.0"):
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/json,application/xml,*/*",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )
        logger.info("DataScraper initialized")

    def scrape_web_page(self, url: str, timeout: int = 30) -> ScrapeResult:
        try:
            logger.info(f"Scraping URL: {url}")
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            result = ScrapeResult(True, data=soup)
            result.metadata = {
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type", "unknown"),
            }
            return result

        except requests.exceptions.RequestException as e:
            return ScrapeResult(False, error=f"Failed to scrape {url}: {e!s}")
        except Exception as e:
            return ScrapeResult(False, error=f"Unexpected error scraping {url}: {e!s}")

    def scrape_api_endpoint(
        self, url: str, params: dict | None = None, timeout: int = 30
    ) -> ScrapeResult:
        try:
            logger.info(f"Scraping API endpoint: {url}")
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError:
                data = response.text

            result = ScrapeResult(True, data=data)
            result.metadata = {"url": url, "status_code": response.status_code}
            return result

        except Exception as e:
            return ScrapeResult(False, error=f"API scraping failed: {e!s}")

    def download_file(self, url: str, timeout: int = 60) -> ScrapeResult:
        """Download a file from a URL without parsing."""
        try:
            logger.info(f"Downloading file: {url}")

            if url.startswith("file://") or "://" not in url:
                # Local file handling
                path_str = url.replace("file://", "")
                path = Path(path_str)
                if not path.exists():
                    return ScrapeResult(False, error=f"Local file not found: {path}")
                content = path.read_bytes()
                result = ScrapeResult(True, data=content)
                result.metadata = {
                    "url": url,
                    "status_code": 200,
                    "content_type": "application/octet-stream",
                }
                return result

            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()

            # Return raw bytes
            result = ScrapeResult(True, data=response.content)
            result.metadata = {
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type", "application/octet-stream"),
            }
            return result
        except Exception as e:
            return ScrapeResult(False, error=f"File download failed: {e!s}")

    def scrape_html_tables(self, url: str, timeout: int = 30) -> ScrapeResult:
        """Scrape HTML tables from a web page as a fallback when structured data is not available.

        Args:
            url: The URL to scrape tables from
            timeout: Request timeout in seconds

        Returns:
            ScrapeResult with list of tables (each table is list of rows, each row is list of cells)
        """
        try:
            logger.info(f"Scraping HTML tables from: {url}")
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            tables = []

            # Find all table elements
            for table in soup.find_all("table"):
                table_data = []
                for row in table.find_all("tr"):
                    row_data = []
                    for cell in row.find_all(["td", "th"]):
                        row_data.append(cell.get_text(strip=True))
                    if row_data:  # Only add non-empty rows
                        table_data.append(row_data)
                if table_data:  # Only add non-empty tables
                    tables.append(table_data)

            if not tables:
                logger.warning(f"No tables found on page: {url}")
                return ScrapeResult(False, error="No HTML tables found on page")

            result = ScrapeResult(True, data=tables)
            result.metadata = {
                "url": url,
                "status_code": response.status_code,
                "table_count": len(tables),
            }
            return result

        except requests.exceptions.RequestException as e:
            return ScrapeResult(False, error=f"Failed to scrape tables from {url}: {e!s}")
        except Exception as e:
            return ScrapeResult(False, error=f"Unexpected error scraping tables: {e!s}")

    def save_data(
        self, data: Any, file_path: str | Path, format: ScrapeFormat | None = None
    ) -> ScrapeResult:
        file_path = Path(file_path)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if format is None:
                ext = file_path.suffix.lower()
                if ext == ".csv":
                    format = ScrapeFormat.CSV
                elif ext == ".xml":
                    format = ScrapeFormat.XML
                else:
                    format = ScrapeFormat.JSON

            if isinstance(data, bytes):
                with open(file_path, "wb") as f:
                    f.write(data)
            elif format == ScrapeFormat.JSON:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            elif format == ScrapeFormat.CSV and isinstance(data, list) and len(data) > 0:
                keys = data[0].keys()
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(data)
            elif format == ScrapeFormat.XML:
                # Simplified XML save
                root = ET.Element("data")
                for i, record in enumerate(data if isinstance(data, list) else [data]):
                    item = ET.SubElement(root, "item", {"id": str(i)})
                    if isinstance(record, dict):
                        for k, v in record.items():
                            child = ET.SubElement(item, k)
                            child.text = str(v)
                tree = ET.ElementTree(root)
                tree.write(file_path, encoding="utf-8", xml_declaration=True)
            else:
                return ScrapeResult(False, error=f"Unsupported format or data structure: {format}")

            return ScrapeResult(True, data=str(file_path))

        except Exception as e:
            return ScrapeResult(False, error=f"Failed to save data: {e!s}")
