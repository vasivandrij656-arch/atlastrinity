import sys
import unittest
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_path))

import logging

from src.brain.logger import SecretFilter


class TestSecretFilter(unittest.TestCase):
    def setUp(self):
        self.filter = SecretFilter()
        self.logger = logging.getLogger("test_logger")
        self.logger.addFilter(self.filter)

    def test_mask_github_token(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="ghp_1234567890abcdef1234567890abcdef1234",
            args=(),
            exc_info=None,
        )
        self.filter.filter(record)
        self.assertNotIn("ghp_1234567890abcdef1234567890abcdef1234", record.msg)
        self.assertIn("[MASKED]", record.msg)

    def test_mask_bearer_token(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Bearer abcdef1234567890",
            args=(),
            exc_info=None,
        )
        self.filter.filter(record)
        self.assertNotIn("Bearer abcdef1234567890", record.msg)
        self.assertIn("[MASKED]", record.msg)

    def test_mask_generic_password(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Password: Dima@1203",
            args=(),
            exc_info=None,
        )
        self.filter.filter(record)
        self.assertNotIn("Dima@1203", record.msg)
        self.assertIn("[MASKED]", record.msg)


if __name__ == "__main__":
    unittest.main()
