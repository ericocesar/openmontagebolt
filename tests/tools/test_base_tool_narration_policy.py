from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.base_tool import BaseTool, ToolResult  # noqa: E402


POLICY_ENV = "MPT_OPENMONTAGE_NARRATION_POLICY"


class GoogleTTSProbe(BaseTool):
    name = "google_tts"
    capability = "tts"
    provider = "google_tts"

    def __init__(self):
        self.received = None

    def execute(self, inputs: dict) -> ToolResult:
        self.received = inputs
        return ToolResult(success=True)


class AivoxTTSProbe(BaseTool):
    name = "aivox_tts"
    capability = "tts"
    provider = "aivox"

    def __init__(self):
        self.received = None

    def execute(self, inputs: dict) -> ToolResult:
        self.received = inputs
        return ToolResult(success=True)


class TTSSelectorProbe(BaseTool):
    name = "tts_selector"
    capability = "tts"
    provider = "selector"

    def __init__(self):
        self.received = None

    def execute(self, inputs: dict) -> ToolResult:
        self.received = inputs
        return ToolResult(success=True)


class HostNarrationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = {
            "mode": "generate",
            "provider": "aivox",
            "voice_id": "masculina-leo-br",
            "voice_mode": "design",
        }

    def test_rejects_direct_call_to_unselected_provider(self):
        tool = GoogleTTSProbe()
        with patch.dict(os.environ, {POLICY_ENV: json.dumps(self.policy)}):
            result = tool.execute({"text": "hello"})

        self.assertFalse(result.success)
        self.assertIn("selected provider 'aivox'", result.error)
        self.assertIsNone(tool.received)

    def test_locks_selector_to_selected_provider_and_voice(self):
        tool = TTSSelectorProbe()
        with patch.dict(os.environ, {POLICY_ENV: json.dumps(self.policy)}):
            result = tool.execute({"text": "hello", "preferred_provider": "google_tts"})

        self.assertTrue(result.success)
        self.assertEqual(tool.received["preferred_provider"], "aivox")
        self.assertEqual(tool.received["allowed_providers"], ["aivox"])
        self.assertEqual(tool.received["voice_id"], "masculina-leo-br")
        self.assertEqual(tool.received["voice_mode"], "design")

    def test_allows_selected_provider_and_overrides_stale_voice(self):
        tool = AivoxTTSProbe()
        with patch.dict(os.environ, {POLICY_ENV: json.dumps(self.policy)}):
            result = tool.execute({"text": "hello", "voice_id": "stale-voice"})

        self.assertTrue(result.success)
        self.assertEqual(tool.received["voice_id"], "masculina-leo-br")
        self.assertEqual(tool.received["voice_mode"], "design")

    def test_blocks_tts_when_narration_is_upload_or_disabled(self):
        for mode in ("upload", "none"):
            tool = AivoxTTSProbe()
            policy = {**self.policy, "mode": mode}
            with self.subTest(mode=mode), patch.dict(os.environ, {POLICY_ENV: json.dumps(policy)}):
                result = tool.execute({"text": "hello"})
                self.assertFalse(result.success)
                self.assertIsNone(tool.received)


if __name__ == "__main__":
    unittest.main()
