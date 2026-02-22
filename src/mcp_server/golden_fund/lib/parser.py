"""
Main Data Parser Interface for Golden Fund
Ported from etl_module/src/parsing/data_parser.py
"""

from pathlib import Path

from .formats import (
    CSVParser,
    ExcelParser,
    HTMLParser,
    JSONParser,
    ParquetParser,
    ParseResult,
    XMLParser,
)


class DataParser:
    def __init__(self) -> None:
        self._parsers: dict[
            str, JSONParser | CSVParser | XMLParser | ExcelParser | ParquetParser | HTMLParser
        ] = {
            "json": JSONParser(),
            "csv": CSVParser(),
            "xml": XMLParser(),
            "xlsx": ExcelParser(),
            "xls": ExcelParser(),
            "parquet": ParquetParser(),
            "html": HTMLParser(),
            "htm": HTMLParser(),
        }

    def parse(self, file_path: str | Path, format_hint: str | None = None) -> ParseResult:
        file_path = Path(file_path)

        if not file_path.exists():
            return ParseResult(False, error=f"File not found: {file_path}")

        if format_hint is None:
            format_hint = file_path.suffix.lstrip(".").lower()

        parser = self._parsers.get(format_hint)
        if not parser:
            return ParseResult(False, error=f"No parser for format: {format_hint}")

        return parser.parse(file_path)
