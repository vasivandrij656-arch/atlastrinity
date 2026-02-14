"""Fast verification script for self-healing modules without heavy deps."""
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
import tempfile
import shutil
import asyncio

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Mock heavy imports before importing our modules
sys.modules["src.brain.memory.chroma_memory"] = MagicMock()
sys.modules["src.brain.core.context"] = MagicMock()
sys.modules["src.brain.healing.system_healing"] = MagicMock()
sys.modules["src.brain.healing.parallel_healing"] = MagicMock()
sys.modules["src.brain.memory.state_manager"] = MagicMock()

# Now import our target modules
from src.brain.healing.log_analyzer import LogAnalyzer
from src.brain.healing.server_manager import ServerManager
from src.brain.healing.modes import HealingMode, ImprovementNote
from src.brain.healing.hypermodule import SelfHealingHypermodule

class TestFastHealing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.notes_path = Path(self.tmp) / "notes.json"
        self.log_dir = Path(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_log_deduplication(self):
        print("\nTesting LogAnalyzer deduplication...")
        analyzer = LogAnalyzer(logs_dir=self.log_dir, notes_path=self.notes_path)
        lines = [
            "2026-02-14 12:00:00 ERROR brain.mcp: ConnectionError: Test Error",
            "2026-02-14 12:00:01 ERROR brain.mcp: ConnectionError: Test Error",
            "2026-02-14 12:00:02 ERROR brain.mcp: ConnectionError: Test Error",
        ]
        notes = analyzer.analyze_chunk(lines)
        # Should return 1 note (first one created), subsequent are updates (return None)
        self.assertEqual(len(notes), 1)
        
        all_notes = analyzer.get_all_notes()
        self.assertEqual(len(all_notes), 1)
        self.assertEqual(all_notes[0].occurrences, 3)
        print("✅ LogAnalyzer deduplication passed")

    def test_log_filtering(self):
        print("\nTesting LogAnalyzer filtering...")
        analyzer = LogAnalyzer(logs_dir=self.log_dir, notes_path=self.notes_path)
        lines = ["2026-02-14 12:00:00 ERROR brain.test: TestError: something broke"]
        analyzer.analyze_chunk(lines)
        
        notes = analyzer.get_pending_notes()
        self.assertEqual(len(notes), 1)
        
        analyzer.mark_addressed(notes[0].id, "fixed")
        pending = analyzer.get_pending_notes()
        self.assertEqual(len(pending), 0)
        print("✅ LogAnalyzer filtering passed")

    async def async_test_server_manager(self):
        print("\nTesting ServerManager state preservation...")
        manager = ServerManager(state_dir=Path(self.tmp))
        state = {"step_id": "test_step", "data": 123}
        
        await manager.save_task_state(state)
        self.assertTrue(manager.has_pending_snapshot())
        
        restored = await manager.restore_task_state()
        self.assertEqual(restored["step_id"], "test_step")
        self.assertEqual(restored["data"], 123)
        
        manager.clear_snapshot()
        self.assertFalse(manager.has_pending_snapshot())
        print("✅ ServerManager state preservation passed")

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFastHealing)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Run async test manually
    loop = asyncio.new_event_loop()
    loop.run_until_complete(TestFastHealing("async_test_server_manager").async_test_server_manager())
    
    if not result.wasSuccessful():
        sys.exit(1)
