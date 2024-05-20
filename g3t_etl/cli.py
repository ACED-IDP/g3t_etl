import importlib
import os
import pathlib
import shutil
import sys
from pathlib import Path

import click
import orjson
from jinja2 import Environment, select_autoescape, PackageLoader

import g3t_etl
from g3t_etl import factory, run_command
from g3t_etl.factory import transform_csv
from g3t_etl.submission_dictionary import spreadsheet_json_schema

from g3t_etl.loader import load_plugins
from importlib.metadata import version as pkg_version

from g3t_etl.transformer import generate_templates, generate_transformer
from g3t_etl.util.local_fhir_db import LocalFHIRDatabase


class OrderCommands(click.Group):

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands)


@click.group(invoke_without_command=True, cls=OrderCommands)
@click.option('--version', is_flag=True, help="Show version")
@click.option('--plugin', help="python module of transformer env:G3T_PLUGIN", envvar="G3T_PLUGIN")
@click.option('--debug', is_flag=True, envvar='G3T_DEBUG', help='Enable debug mode. G3T_DEBUG environment variable can also be used.')
@click.pass_context
def cli(ctx, version, plugin, debug: bool):
    """Create ACED metadata submissions."""
    if version:
        _ = pkg_version('g3t-etl')
        click.echo(_)
        ctx.exit()

    # If no arguments are given, g3t should return the help menu
    if len(sys.argv[1:]) == 0:
        click.echo(ctx.get_help())
        ctx.exit()

    ctx.ensure_object(dict)
    if plugin:
        load_plugins([plugin])
        plugin_module = importlib.import_module(plugin)
        plugin_path = os.path.dirname(plugin_module.__file__)
        plugin_path = pathlib.Path(plugin_path).relative_to(os.getcwd())
        click.secho(f"Loaded {plugin} {plugin_path}", fg="green", file=sys.stderr)
        ctx.obj['plugin'] = plugin
        ctx.obj['plugin_path'] = plugin_path
    else:
        click.secho("No plugin loaded", fg="yellow", file=sys.stderr)
    ctx.obj['debug'] = debug


@cli.command('generate')
@click.argument('input_path', type=click.Path(), default=None,
                required=False)
@click.argument('plugin_path', type=click.Path(), default=None,
                required=False)
@click.option('--overwrite', default=False, show_default=True, is_flag=True,
              help='overwrite existing files')
@click.pass_context
def spreadsheet_json_schema_cli(ctx, input_path: str, plugin_path: str, overwrite: bool):
    """Code generation. Create python resources based on dictionary spreadsheet.
    \b
    <plugin_path>/<submission>.schema.json
    <plugin_path>/<submission>.py
    <plugin_path>/<submission>_transformer.py
    <plugin_path>/templates/<Resource>.yaml.jinja2
    \b
    Use this command to track changes to the data dictionary.
    INPUT_PATH: where to read master spreadsheet file
    PLUGIN_PATH: directory where to write submission schema and code
    """
    output_path = None
    try:
        #
        # create schema
        #
        if not input_path:
            input_path = factory.default_dictionary_path

        input_path = Path(input_path)
        assert input_path.exists(), f"Spreadsheet not found at {input_path},"\
                                    " please see README in docs/ for instructions."

        schema = spreadsheet_json_schema(input_path)

        if not plugin_path:
            plugin_path = ctx.obj.get('plugin_path', None)

        plugin_path = Path(plugin_path)
        plugin_path.mkdir(exist_ok=True, parents=True)
        assert plugin_path.exists(), f"Plugin path not found at {plugin_path},"
        assert plugin_path.is_dir(), f"Plugin path not a directory at {plugin_path},"

        output_path = plugin_path / (input_path.stem + '.json')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as fp:
            fp.write(orjson.dumps(schema, option=orjson.OPT_INDENT_2).decode())

        click.secho(f"Transformed {input_path} into jsonschema file in {output_path}",
                    fg='green', file=sys.stderr)
        #
        # generate pydantic model from schema
        #
        submission_source_path = plugin_path / (input_path.stem + '.py').replace('-', '_')
        if pathlib.Path(submission_source_path).exists() and not overwrite:
            click.secho(f"Skipping {submission_source_path}. It already exists. Use --overwrite to force.", fg='yellow', file=sys.stderr)
        else:
            cmd = f"datamodel-codegen  --input {output_path} --input-file-type jsonschema  "\
                  f"--output {submission_source_path} --field-extra-keys json_schema_extra"
            click.secho(f"Running: {cmd}", fg='yellow', file=sys.stderr)
            return_code, stdout, stderr = run_command(cmd)
            if return_code:
                click.secho(f"Error running {cmd}: {stderr} {stdout}", fg='red')
            click.secho(f"Created: {submission_source_path}", fg='green', file=sys.stderr)

        # generate default transformers
        generate_transformer(submission_source_path, overwrite=overwrite)

        # create templates
        target_template_dir = pathlib.Path(plugin_path) / 'templates'
        target_template_dir.mkdir(parents=True, exist_ok=True)
        generate_templates(target_template_dir=target_template_dir, overwrite=overwrite)

    except Exception as e:
        click.secho(f"Error parsing {input_path}: {e}", fg='red')
        print(ctx.obj)
        if ctx.obj.get('debug', False):
            raise e


@cli.command('templates')
@click.option('--verbose', default=False, show_default=True, is_flag=True,
              help='verbose output')
@click.option('--overwrite', default=False, show_default=True, is_flag=True,
              help='overwrite existing files')
@click.argument('plugin_path', type=click.Path(exists=True), default=None,
                required=True)
@click.pass_context
def generate_templates_cli(ctx, plugin_path, verbose: bool, overwrite: bool):
    """Code generation. Create templates from submission schema into <plugin_path>/templates.
    \b
    PLUGIN_PATH: directory containing plugin
    """
    try:
        #
        # create templates
        #
        target_template_dir = pathlib.Path(plugin_path) / 'templates'
        target_template_dir.parent.mkdir(parents=True, exist_ok=True)

        generate_templates(target_template_dir=target_template_dir, overwrite=overwrite)
    except Exception as e:
        click.secho(f"Error generating templates: {e}", fg='red')
        if ctx.obj.get('debug', False):
            raise e


@cli.command('transform')
@click.argument('input_path', type=click.Path(exists=True, dir_okay=False),
                default=None, required=True)
@click.argument('output_path', type=click.Path(dir_okay=True), default='META', required=False)
@click.option('--verbose', default=False, show_default=True, is_flag=True,
              help='verbose output')
@click.pass_context
def transform_csv_cli(ctx, input_path: str, output_path: str, verbose: bool):
    """Transform csv based on data dictionary to FHIR.

    \b
    INPUT_PATH: where to read spreadsheet. required, (convention data/raw/XXXX.xlsx)
    OUTPUT_PATH: where to write FHIR. default: META/
    """

    try:
        if ctx.obj.get('debug', False):
            verbose = True
        transformation_results = transform_csv(input_path=input_path, output_path=output_path, verbose=verbose)
        if not transformation_results.transformer_errors and not transformation_results.validation_errors:
            click.secho(f"Transformed {input_path} into {output_path}", fg='green', file=sys.stderr)
        else:
            click.secho(f"Error transforming {input_path}")
            if verbose:
                click.secho(f"Validation errors: {transformation_results.validation_errors}", fg='red')
                click.secho(f"Transformer errors: {transformation_results.transformer_errors}", fg='red')
    except Exception as e:
        click.secho(f"Error generating templates: {e}", fg='red')
        if ctx.obj.get('debug', False):
            raise e


@cli.command('dataframe')
@click.argument('input_path',
                default='META',
                type=click.Path(exists=True, dir_okay=True),
                required=False)
@click.argument('output_path',
                type=click.Path(dir_okay=False),
                required=True)
@click.option('--verbose',
              default=False,
              show_default=True, is_flag=True,
              help='verbose output')
@click.pass_context
def extract_cli(ctx, input_path: str, output_path: str, verbose: bool):
    """Create flattened dataframe (experimental).

    \b
    INPUT_PATH: where to read FHIR  default: META/
    OUTPUT_PATH: where to write db.
    """
    try:
        db = LocalFHIRDatabase(db_name=pathlib.Path(output_path))
        db.load_ndjson_from_dir(input_path)
        click.secho(f"Exported {input_path} into {output_path}", fg='green', file=sys.stderr)
    except Exception as e:
        click.secho(f"Error generating dataframe: {e}", fg='red')
        if ctx.obj.get('debug', False):
            raise e


if __name__ == '__main__':
    cli()
