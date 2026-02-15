from datetime import datetime
from typing import Any


class StorageResult:
    """Result container for storage operations."""

    def __init__(
        self, success: bool, target: str, data: Any | None = None, error: str | None = None
    ):
        self.success = success
        self.target = target
        self.data = data
        self.error = error
        self.timestamp = datetime.now()

    def __repr__(self) -> str:
        if self.success:
            return f"StorageResult(success=True, target={self.target})"
        return f"StorageResult(success=False, target={self.target}, error={self.error})"

    def __str__(self) -> str:
        if not self.success:
            return f"Error ({self.target}): {self.error}"
        
        if not self.data:
            return f"Success ({self.target}): No data"
            
        results = self.data.get("results", [])
        if isinstance(results, list) and results:
            import json
            return json.dumps(results, indent=2, default=str)
            
        return f"Success ({self.target}): {self.data}"
