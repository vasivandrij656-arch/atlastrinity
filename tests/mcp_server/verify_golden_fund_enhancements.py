import asyncio
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import json

from src.mcp_server.golden_fund.lib.connectors.ckan_connector import CKANConnector
from src.mcp_server.golden_fund.lib.scraper import DataScraper, ScrapeResult
from src.mcp_server.golden_fund.tools.ingest import search_and_ingest

class TestGoldenFundEnhancements(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.portal_url = "https://data.gov.ua/api/3"
        self.connector = CKANConnector(self.portal_url)

    def test_ckan_search_params(self):
        """Verify that search_packages correctly formats parameters."""
        with patch.object(self.connector.session, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"success": True, "result": {"results": []}}
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            self.connector.search_packages(
                "query", 
                rows=5, 
                filters={"groups": "legal"}, 
                sort="metadata_modified desc"
            )

            args, kwargs = mock_get.call_args
            params = kwargs.get('params')
            self.assertEqual(params['q'], "query")
            self.assertEqual(params['rows'], 5)
            self.assertEqual(params['fq'], "groups:legal")
            self.assertEqual(params['sort'], "metadata_modified desc")

    @patch('src.mcp_server.golden_fund.lib.scraper.KeychainBridge')
    def test_scraper_auth_retry(self, MockKeychainBridge):
        """Verify that DataScraper retries with credentials on 401."""
        mock_bridge = MockKeychainBridge.return_value
        mock_bridge.get_credential_for_domain.return_value = MagicMock(
            secret="test_secret", 
            source="macos_keychain"
        )

        scraper = DataScraper()
        
        with patch.object(scraper.session, 'get') as mock_get:
            # First response: 401
            mock_401 = MagicMock()
            mock_401.status_code = 401
            
            # Second response: 200
            mock_200 = MagicMock()
            mock_200.status_code = 200
            mock_200.content = b"content"
            mock_200.headers = {"Content-Type": "text/plain"}

            mock_get.side_effect = [mock_401, mock_200]

            res = scraper.scrape_web_page("https://example.com/data")
            
            self.assertTrue(res.success)
            self.assertEqual(mock_get.call_count, 2)
            self.assertIn("Authorization", scraper.session.headers)
            self.assertEqual(scraper.session.headers["Authorization"], "Bearer test_secret")

    @patch('src.mcp_server.golden_fund.tools.ingest.CKANConnector')
    @patch('src.mcp_server.golden_fund.tools.ingest.ingest_dataset')
    async def test_search_and_ingest(self, mock_ingest, MockConnector):
        """Verify that search_and_ingest orchestrates the process correctly."""
        mock_conn = MockConnector.return_value
        mock_conn.search_packages.return_value = [
            {"name": "pkg1", "title": "Package 1", "resources": [{"format": "CSV", "url": "http://pkg1.csv"}]}
        ]
        mock_conn.find_resources_by_format.return_value = [{"format": "CSV", "url": "http://pkg1.csv"}]
        mock_conn.get_resource_url.return_value = "http://pkg1.csv"
        
        mock_ingest.return_value = "Ingestion Success"

        result = await search_and_ingest("test_query", max_datasets=1)
        
        self.assertIn("Package 1", result)
        self.assertIn("Ingestion Success", result)
        mock_ingest.assert_called_once()
        kwargs = mock_ingest.call_args.kwargs
        self.assertEqual(kwargs['url'], "http://pkg1.csv")
        self.assertEqual(kwargs['type'], "csv")

if __name__ == "__main__":
    unittest.main()
