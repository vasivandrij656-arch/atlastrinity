"""
Opendatabot Connector for Golden Fund
Handles interaction with Opendatabot API and provides simulation data for testing.
"""

import logging
from typing import Any, cast
import requests
from src.brain.auth.keychain_bridge import KeychainBridge

logger = logging.getLogger("golden_fund.connectors.opendatabot")

class OpendatabotConnector:
    def __init__(self, api_key: str | None = None):
        self.base_url = "https://opendatabot.ua/api/v3"
        self.keychain = KeychainBridge()
        self.api_key = api_key or self._get_api_key_from_keychain()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        self.session.headers.update({"Accept": "application/json"})
        
        logger.info(f"Opendatabot Connector initialized (API Key: {'set' if self.api_key else 'missing, simulation mode only'})")

    def _get_api_key_from_keychain(self) -> str | None:
        cred = self.keychain.get_credential_for_domain("opendatabot.ua")
        return cred.secret if cred else None

    def search_company(self, query: str) -> list[dict[str, Any]]:
        """
        Search for a company by name or EDRPOU.
        """
        if not self.api_key:
            return self._get_simulation_data(query)

        url = f"{self.base_url}/company"
        params = {"q": query}
        try:
            response = self.session.get(url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            return cast("list[dict[str, Any]]", data.get("data", []))
        except Exception as e:
            logger.error(f"Opendatabot search failed: {e}")
            return self._get_simulation_data(query)

    def _get_simulation_data(self, query: str) -> list[dict[str, Any]]:
        """
        Returns high-impact simulation data for testing and demonstration.
        """
        logger.info(f"Returning Opendatabot simulation data for: {query}")
        
        # High-impact sample: A real estate developer with address and owners
        sample_data = [
            {
                "full_name": "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ 'КАН ДЕВЕЛОПМЕНТ'",
                "short_name": "ТОВ 'КАН ДЕВЕЛОПМЕНТ'",
                "edrpou": "37715423",
                "status": "зареєстровано",
                "address": "Україна, 01014, місто Київ, вуд.Болсуновська, будинок 13-15",
                "director": "Ніконов Ігор Володимирович",
                "owners": ["Ніконов Ігор Володимирович"],
                "activities": ["Організація будівництва будівель"],
                "source": "opendatabot_simulation"
            },
            {
                "full_name": "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ 'СТОЛИЦЯ ГРУП'",
                "short_name": "ТОВ 'СГ'",
                "edrpou": "36175133",
                "status": "зареєстровано",
                "address": "Україна, 04071, місто Київ, вул.Набережно-Хрещатицька, будинок 9",
                "director": "Молчанова Владислава Борисівна",
                "owners": ["Молчанова Владислава Борисівна"],
                "activities": ["Будівництво житлових і нежитлових будівель"],
                "source": "opendatabot_simulation"
            }
        ]
        
        # Filter by simple string match for "simulation" search feeling
        results = [d for d in sample_data if query.lower() in str(d).lower()]
        return results if results else sample_data
