"""
Entity Extraction Module for Golden Fund
Uses LLM to extract entities and relationships from text for Knowledge Graph construction.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, cast

# Ensure project root is in path to import providers
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.providers.copilot import CopilotLLM
except ImportError:
    CopilotLLM = None

logger = logging.getLogger("golden_fund.entity_extractor")


class EntityExtractor:
    def __init__(self):
        self.llm = None
        if CopilotLLM:
            try:
                self.llm = CopilotLLM()
                logger.info("EntityExtractor initialized with CopilotLLM")
            except Exception as e:
                logger.warning(f"Failed to initialize CopilotLLM: {e}")
        else:
            logger.warning("CopilotLLM not available. Entity Extraction will be disabled.")

    def extract(self, text: str, source_url: str = "") -> dict[str, Any]:
        """
        Extracts entities and relationships from text.
        Returns a dict with 'entities' and 'relationships' keys.
        """
        if not self.llm:
            return {"entities": [], "relationships": []}

        # Truncate text if too long to fit context (approx 12k tokens max, use 8k chars safe limit)
        text_sample = text[:12000]

        prompt = f"""Extract key entities and relationships from the following text for a Knowledge Graph.
Source: {source_url}

Target Entities:
- Person
- Organization
- Location
- Technology/Tool
- Concept (Key Technical Terms or Abstract Ideas)

Target Relationships:
- (Entity A) -> [RELATIONSHIP] -> (Entity B)

Format output as JSON:
{{
  "entities": [
    {{"name": "...", "type": "...", "description": "..."}}
  ],
  "relationships": [
    {{"source": "...", "target": "...", "relation": "..."}}
  ]
}}

Text:
{text_sample}
"""
        try:
            response = self.llm.invoke(
                [
                    SystemMessage(
                        content="You are a Knowledge Graph extraction engine. Output valid JSON only."
                    ),
                    HumanMessage(content=prompt),
                ]
            )

            content = cast("str", response.content).strip()
            # Cleanup markdown code blocks if present
            content = content.removeprefix("```json")
            content = content.removeprefix("```")
            content = content.removesuffix("```")

            data = json.loads(content.strip())
            return data

        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {"entities": [], "relationships": []}
