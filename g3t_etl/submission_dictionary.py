import os

import pathlib
import re

import inflection
import numpy as np
import pandas as pd

import gen3_tracker.config as g3t_config


def spreadsheet_json_schema(input_path: pathlib.Path, sheet_main: str = 'fhir_mapping') -> dict:
    """Read spreadsheet, create schema."""
    if isinstance(input_path, str):
        input_path = pathlib.Path(input_path)
    df = read_excel_worksheet(input_path, sheet_main)
    df = df.replace({np.nan: ""})
    schema = create_jsonschema(df, title=inflection.camelize(input_path.stem))
    return schema


def read_excel_worksheet(file_path, sheet_name) -> pd.DataFrame:
    """
    Read a specific worksheet from an Excel file and return its contents as a pandas DataFrame.

    Parameters:
    - file_path (str): The path to the Excel file.
    - sheet_name (str): The name of the worksheet to read.

    Returns:
    - pd.DataFrame: The contents of the specified worksheet as a DataFrame.
    """
    # Use the pandas read_excel function with the sheet_name parameter
    worksheet_data = pd.read_excel(file_path, sheet_name)
    return worksheet_data


def _map_type(dtype: str) -> str:
    """Common types to jsonschema types."""
    if 'int' in dtype:
        return 'integer'
    if 'float' in dtype:
        return 'number'
    if 'datetime' in dtype:
        return 'string'

    assert dtype in ['string', 'number', 'object', 'array', 'boolean', 'null'], f"unknown dtype {dtype}"

    return dtype


def _map_name(name):
    """Enforce legal (python) property name."""
    _ = re.search(r'[_a-zA-Z][_a-zA-Z0-9]*', name)
    if _ is None:
        raise Exception(f"illegal property name {name}")
    return name


def create_jsonschema(input_df,
                      name_column: str = 'csv_column_name',
                      type_column: str = 'csv_type',
                      description_column: str = 'csv_description',
                      title: str = 'submission'
                      ) -> dict:
    """
    Derive jsonschema from spreadsheet.

    Parameters:
    - input_df (pd.DataFrame): The input DataFrame to be split.
    - output_directory (Path): The directory to save the jsonschema.
    - name_column (str): The name of the column containing the submitted property name.
    - type_column (str): The name of the column containing the submitted type name.

    """
    config = g3t_config.default()
    project_id = config.gen3.project_id
    if not project_id:
        project_id = os.environ.get('G3T_PROJECT_ID', None)
    assert project_id, "project_id not set, please initialize g3t or set environment variable G3T_PROJECT_ID"

    schema = {
        "$id": f"https://aced-idp.org/{project_id}/submission.schema.json",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        "type": "object",
        "description": f"Raw tabular data submitted by {config.gen3.project_id}",
        "properties": {}
    }

    # Iterate through each row in the DataFrame, create property in schema
    for index, row in input_df.iterrows():
        name = _map_name(row[name_column])
        description = row[description_column]
        dtype = row[type_column]
        extra_fields = [_ for _ in row.index.tolist() if _ not in [name_column, type_column, description_column]]
        property_schema = {
            "type": _map_type(dtype),
            "description": description
        }
        json_schema_extra = {}
        for extra_field in extra_fields:
            if row[extra_field] == "" or pd.isna(row[extra_field]):
                continue
            json_schema_extra[extra_field] = row[extra_field]
        property_schema['json_schema_extra'] = json_schema_extra
        schema['properties'][name] = property_schema
    return schema
