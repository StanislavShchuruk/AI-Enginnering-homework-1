"""Keep the whole test suite independent of local secret files."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def disable_dotenv_reads() -> Iterator[None]:
    with patch("ai_project.config.load_dotenv", return_value=False):
        yield
