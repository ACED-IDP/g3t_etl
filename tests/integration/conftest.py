import pathlib

import pytest


@pytest.fixture
def plugins() -> list[str]:
    """Return a list of plugins."""
    return ['sample_transformer.transformer']


@pytest.fixture
def test_fixture_paths() -> list[str]:
    """Return a path to dummy data."""
    return [
        pathlib.Path(_) for _ in
        [
            'tests/fixtures/sample_dataset/dummy_data_30pid.csv',
            'tests/fixtures/sample_dataset/dummy_data_200pid.csv',
            'tests/fixtures/sample_dataset/dummy_data_500pid.csv',
        ]
    ]


@pytest.fixture
def test_fixture_fhir_path() -> str:
    """Return a path to dummy data."""
    return 'tests/fixtures/sample_dataset-FHIR'
