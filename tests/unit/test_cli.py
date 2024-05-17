from click.testing import CliRunner

from g3t_etl.cli import cli


def test_cli():
    """Ensure we can run the cli."""
    runner = CliRunner()
    result = runner.invoke(cli, '--help'.split())
    assert result.exit_code == 0


def test_dictionary_cli():
    """Ensure we can run the cli."""
    runner = CliRunner()
    result = runner.invoke(cli, 'generate --help'.split())
    assert result.exit_code == 0


def test_transform_cli():
    """Ensure we can run the cli."""
    runner = CliRunner()
    result = runner.invoke(cli, 'transform --help'.split())
    assert result.exit_code == 0
