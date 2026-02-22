"""
Unified Data Format Parsers for Golden Fund
Ported and consolidated from etl_module/src/parsing/formats/
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd


class ParseResult:
    """Result container for parsed data."""

    def __init__(self, success: bool, data: Any | None = None, error: str | None = None):
        self.success = success
        self.data = data
        self.error = error
        self.metadata: dict[str, Any] = {}


class JSONParser:
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        try:
            # Try pandas first for clear structure
            try:
                df = pd.read_json(file_path, **kwargs)
                return ParseResult(True, data=df)
            except ValueError:
                # Fallback to standard json
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                return ParseResult(True, data=data)
        except Exception as e:
            return ParseResult(False, error=f"JSON parse error: {e}")


class CSVParser:
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        encodings = ["utf-8", "latin1", "cp1252", "iso-8859-1"]
        last_error = ""

        # Check for delimiter sniffing
        sep = kwargs.get("sep", ",")

        for encoding in encodings:
            try:
                # Basic read
                df = pd.read_csv(
                    file_path, encoding=encoding, on_bad_lines="skip", sep=sep, **kwargs
                )

                # If only 1 column, maybe wrong separator?
                if len(df.columns) == 1 and sep == ",":
                    # Try semicolon
                    try:
                        df_semi = pd.read_csv(
                            file_path, encoding=encoding, on_bad_lines="skip", sep=";"
                        )
                        if len(df_semi.columns) > 1:
                            df = df_semi
                    except:
                        pass

                return ParseResult(True, data=df)
            except UnicodeDecodeError:
                continue
            except Exception as e:
                last_error = str(e)
                # Don't break immediately, try other encodings might help (unlikely for CSV structure errors but possible)
                continue

        return ParseResult(False, error=f"CSV parse error: {last_error or 'Unknown encoding'}")


class XMLParser:
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        try:
            tree = ET.parse(file_path)  # nosec B314
            root = tree.getroot()
            data = self._element_to_dict(root)
            return ParseResult(True, data=data)
        except Exception as e:
            return ParseResult(False, error=f"XML parse error: {e}")

    def _element_to_dict(self, element: ET.Element) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if element.attrib:
            result["@attributes"] = element.attrib

        for child in element:
            child_data = self._element_to_dict(child)
            if child.tag in result:
                current_val = result[child.tag]
                if isinstance(current_val, list):
                    current_val.append(child_data)
                else:
                    result[child.tag] = [current_val, child_data]
            else:
                result[child.tag] = child_data

        if element.text and element.text.strip():
            if result:
                result["#text"] = element.text.strip()
            else:
                return {"#text": element.text.strip()}
        return result


class ExcelParser:
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        try:
            # Read all sheets by default if not specified
            sheet_name = kwargs.get("sheet_name")
            df_dict = pd.read_excel(file_path, sheet_name=sheet_name, **kwargs)

            if isinstance(df_dict, dict):
                # Multiple sheets, return dict of DataFrames
                return ParseResult(True, data=df_dict)
            # Single DataFrame
            return ParseResult(True, data=df_dict)
        except Exception as e:
            return ParseResult(False, error=f"Excel parse error: {e}")


class ParquetParser:
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        try:
            df = pd.read_parquet(file_path, **kwargs)
            return ParseResult(True, data=df)
        except Exception as e:
            return ParseResult(False, error=f"Parquet parse error: {e}")


class HTMLParser:
    """Parser for HTML tables using pandas.read_html."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        try:
            # read_html returns a list of DataFrames
            dfs = pd.read_html(str(file_path), **kwargs)
            if not dfs:
                return ParseResult(False, error="No tables found in HTML")

            # Combine all tables if multiple, or just take the largest one
            if len(dfs) > 1:
                # Heuristic: largest table is likely the data
                df = max(dfs, key=len)
            else:
                df = dfs[0]

            return ParseResult(True, data=df)
        except Exception as e:
            return ParseResult(False, error=f"HTML table parse error: {e}")
