from typing import List

import pytest


@pytest.fixture
def python_source_directories() -> List[str]:
    """Directories to scan with flake8."""
    return ["sample_transformer", "tests"]


@pytest.fixture
def data_dictionary_input_path() -> str:
    """Path to the data dictionary."""
    return "tests/fixtures/sample_data_dictionary.xlsx"
