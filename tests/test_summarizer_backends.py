import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lynx_memory import config, summarizer
from lynx_memory.hooks import on_session_end


class SummaryBackendTest(unittest.TestCase):
    def test_turn_summary_openai_backend_uses_openai_key(self):
        with mock.patch.dict(
            os.environ,
            {"SUMMARY_BACKEND": "openai", "OPENAI_API_KEY": "sk-test"},
            clear=True,
        ), mock.patch.object(
            summarizer,
            "_summarize_via_openai",
            return_value=("summary", "openai", "gpt-test"),
        ) as openai_call:
            self.assertEqual(
                summarizer.summarize_with_source("user", "assistant"),
                ("summary", "openai", "gpt-test"),
            )
            openai_call.assert_called_once_with("user", "assistant")

    def test_empty_openai_base_url_uses_default_url(self):
        seen_kwargs = {}

        class FakeResponses:
            def create(self, **kwargs):
                class Resp:
                    output_text = "summary"

                return Resp()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                seen_kwargs.update(kwargs)
                self.responses = FakeResponses()

        with mock.patch.dict(
            os.environ,
            {
                "SUMMARY_BACKEND": "openai",
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_BASE_URL": "",
            },
            clear=True,
        ), mock.patch("openai.OpenAI", FakeOpenAI):
            self.assertEqual(
                summarizer._summarize_via_openai("user", "assistant"),
                ("summary", "openai", "gpt-4o-mini"),
            )
            self.assertEqual(seen_kwargs["base_url"], "https://api.openai.com/v1")

    def test_session_summary_openai_backend_uses_openai(self):
        with mock.patch.dict(
            os.environ,
            {"SUMMARY_BACKEND": "openai", "OPENAI_API_KEY": "sk-test"},
            clear=True,
        ), mock.patch.object(
            on_session_end, "_summarize_via_openai", return_value="session summary"
        ) as openai_call, mock.patch.object(
            on_session_end, "_summarize_via_sdk", return_value=""
        ) as sdk_call:
            self.assertEqual(on_session_end._summarize("conversation"), "session summary")
            openai_call.assert_called_once_with("conversation")
            sdk_call.assert_not_called()

    def test_store_env_overrides_inherited_environment(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            (data_dir / ".env").write_text("OPENAI_API_KEY=from-file\n")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "from-process"}, clear=True):
                config.load_env(data_dir)
                self.assertEqual(os.environ["OPENAI_API_KEY"], "from-file")


if __name__ == "__main__":
    unittest.main()
