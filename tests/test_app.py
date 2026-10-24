import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from ai_project.cli import main
from ai_project.config import Settings
from ai_project.providers import MockProvider, create_provider
from ai_project.service import AIService


class AppTests(unittest.TestCase):
    def test_settings_from_environment(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "mock", "AI_MODEL": "custom"}):
            self.assertEqual(Settings.from_env(), Settings(provider="mock", model="custom"))

    def test_prompt_is_normalized(self):
        self.assertEqual(AIService(MockProvider()).run("  hello  "), "[mock] You said: hello")

    def test_empty_prompt_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            AIService(MockProvider()).run(" \n ")

    def test_unknown_provider_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            create_provider(Settings(provider="unknown"))

    def test_cli(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"AI_PROVIDER": "mock"}), redirect_stdout(output):
            self.assertEqual(main(["hello"]), 0)
        self.assertIn("[mock] You said: hello", output.getvalue())

    def test_cli_invalid_prompt(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(["   "])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
