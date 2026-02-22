"""
Tests for KyivChronicle: Absolute Time Synchronization.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from src.brain.neural_core.chronicle import KyivChronicle


@pytest.mark.asyncio
async def test_kyiv_time_format():
    chronicle = KyivChronicle()
    now_iso = chronicle.get_iso_now()
    # Format: 2026-02-22T23:53:02+02:00
    assert "T" in now_iso
    assert (
        "+02:00" in now_iso or "+03:00" in now_iso
    )  # Depending on DST (though Ukraine currently stays on EET)


@pytest.mark.asyncio
async def test_time_sync_fallback():
    chronicle = KyivChronicle()
    await chronicle.sync_time()
    # verify it works or handles error
    assert hasattr(chronicle, "last_sync")


def test_kyiv_timezone_offset():
    chronicle = KyivChronicle()
    # Ukraine is UTC+2 or UTC+3
    kyiv_now = chronicle.get_now()
    diff = kyiv_now.utcoffset().total_seconds() / 3600
    assert diff in [2.0, 3.0]
