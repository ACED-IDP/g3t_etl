"""Factory for creating a transformer."""
import os
import pathlib
from typing import Callable

import numpy as np
import pandas
import orjson
import json
import importlib
from pydantic import BaseModel, ConfigDict, ValidationError

import decimal
from fhir.resources.fhirresourcemodel import FHIRAbstractModel

from g3t_etl import get_emitter, print_transformation_error, print_validation_error, close_emitters, Transformer
from g3t_etl.transformer import DEFAULT_HELPER, TemplateHelper

transformers: list[Callable[..., Transformer]] = []
default_dictionary_path: None


def default_transformer():
    """Default transformer."""
    return transformers[0]


def register(transformer: Callable[..., Transformer], dictionary_path: str = None) -> None:
    """Register a new transformer."""
    transformers.append(transformer)
    global default_dictionary_path
    default_dictionary_path = dictionary_path


def unregister(transformer: Callable[..., Transformer]) -> None:
    """Unregister a transformer."""
    transformers.remove(transformer)


class TransformationResults(BaseModel):
    """Summarize the transformation results."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    parsed_count: int
    emitted_count: int
    validation_errors: list[ValidationError]
    transformer_errors: list[ValidationError]


def remove_empty_dicts(data):
    """
    Recursively remove empty dictionaries and lists from nested data structures.
    """
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                cleaned = remove_empty_dicts(v)
                # keep non-empty structures or zero
                if cleaned or cleaned == 0:
                    new_data[k] = cleaned
            # keep values that are not empty or zero
            elif v or v == 0:
                new_data[k] = v
        return new_data

    elif isinstance(data, list):
        cleaned_list = [remove_empty_dicts(item) for item in data]
        cleaned_list = [item for item in cleaned_list if item or item == 0]  # remove empty items
        return cleaned_list if cleaned_list else None  # return none if list is empty

    else:
        return data


def convert_decimal_to_float(data):
    """Convert pydantic Decimal to float"""
    if isinstance(data, dict):
        return {k: convert_decimal_to_float(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_decimal_to_float(item) for item in data]
    elif isinstance(data, decimal.Decimal):
        return float(data)
    else:
        return data


def convert_value_quantity_to_float(data):
    """
    Recursively converts all 'valueQuantity' -> 'value' fields in a nested dictionary or list
    from strings to floats.
    """
    if isinstance(data, list):
        return [convert_value_quantity_to_float(item) for item in data]
    elif isinstance(data, dict):
        for key, value in data.items():
            if key == 'valueQuantity' and isinstance(value, dict) and 'value' in value:
                if isinstance(value['value'], str):
                    # and value['value'].replace('.', '', 1).isdigit():
                    value['value'] = float(value['value'])
            else:
                data[key] = convert_value_quantity_to_float(value)
    return data


def convert_value_to_float(data):
    """
    Recursively converts all general 'entity' -> 'value' fields in a nested dictionary or list
    from strings to float or int.
    """
    if isinstance(data, list):
        return [convert_value_to_float(item) for item in data]
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict) and 'value' in value:
                if isinstance(value['value'], str):
                    if value['value'].replace('.', '').replace('-', '', 1).isdigit() and "." in value['value']:
                        value['value'] = float(value['value'])
                    elif value['value'].replace('.', '').replace('-', '', 1).isdigit() and "." not in value['value']:
                        value['value'] = int(value['value'])
            else:
                data[key] = convert_value_to_float(value)
    return data


def validate_fhir_resource_from_type(resource_type: str, resource_data: dict) -> FHIRAbstractModel:
    """
    Generalized function to validate any FHIR resource type using its name.
    """
    try:
        resource_module = importlib.import_module(f"fhir.resources.{resource_type.lower()}")
        resource_class = getattr(resource_module, resource_type)
        return resource_class.model_validate(resource_data)

    except (ImportError, AttributeError) as e:
        raise ValueError(f"Invalid resource type: {resource_type}. Error: {str(e)}")


def transform_csv(input_path: pathlib.Path,
                  output_path: pathlib.Path,
                  already_seen: set = None,
                  verbose: bool = False) -> TransformationResults:
    """Transform a CSV file to FHIR templates."""

    if already_seen is None:
        already_seen = set()

    emitters = {}

    # clean up the data: remove leading/trailing spaces, replace NaN with None
    df = pandas.read_csv(input_path, skipinitialspace=True, skip_blank_lines=True, comment="#", dtype=str)
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    df = df.replace({np.nan: None})

    # create a list of dictionaries
    records = df.to_dict(orient='records')

    parsed_count = 0
    emitted_count = 0
    validation_errors = []
    transformer_errors = []
    research_study = None
    try:
        transformer_class = default_transformer()
        template_helper = TemplateHelper(transformer_class.template_dir())
        transformer = transformer_class(helper=DEFAULT_HELPER, template_helper=template_helper)
        research_study = transformer.create_research_study()
        already_seen.add(research_study.id)
        # get_emitter(emitters, research_study.resource_type, str(output_path), verbose=False).write(research_study.json() + "\n")
        get_emitter(emitters, research_study.get_resource_type(), str(output_path), verbose=False).write(
            research_study.model_dump_json() + "\n")
        emitted_count += 1

    except ValidationError as e:
        transformer_errors.append(e)
        print_transformation_error(e, parsed_count, input_path, research_study, verbose)
        raise e

    # setup profiling
    # start = datetime.datetime.now()
    # pr = cProfile.Profile()
    # pr.enable()

    for record in records:

        try:
            transformer = transformer_class(**record, helper=DEFAULT_HELPER, template_helper=template_helper)
            parsed_count += 1

        except ValidationError as e:
            validation_errors.append(e)
            print_validation_error(e, parsed_count, input_path, record, verbose)
            raise e

        try:
            resources = transformer.transform(research_study=research_study)
            assert resources is not None, f"transformer {transformer} returned None"
            assert len(resources) > 0, f"transformer {transformer} returned empty list"
            for resource in resources:
                if resource.id in already_seen:
                    continue
                already_seen.add(resource.id)
                resource_type = resource.get_resource_type()

                raw_resource_json = resource.model_dump_json()
                cleaned_resource_dict = remove_empty_dicts(orjson.loads(raw_resource_json))

                try:
                    validated_resource = validate_fhir_resource_from_type(resource_type, cleaned_resource_dict).model_dump_json()
                except ValueError as e:
                    print(f"Validation failed for {resource_type}: {e}")
                    continue

                # handle pydantic Decimal cases
                validated_resource = convert_decimal_to_float(orjson.loads(validated_resource))
                validated_resource = convert_value_to_float(validated_resource)
                validated_resource = orjson.dumps(validated_resource).decode("utf-8")

                if resource_type == "Observation": # if Observation - always append to the ndjson file
                    output_file = os.path.join(output_path, "Observation.ndjson")
                    if os.path.exists(output_file): # possibly don't need this check
                        get_emitter(emitters, resource_type, str(output_path), verbose=False, file_mode="a").write(
                            validated_resource + "\n")
                    else:
                        get_emitter(emitters, resource_type, str(output_path), verbose=False, file_mode="w").write(
                            validated_resource + "\n")
                else:
                    get_emitter(emitters, resource_type, str(output_path), verbose=False).write(validated_resource + "\n")

                emitted_count += 1
        except ValidationError as e:
            transformer_errors.append(e)
            print_transformation_error(e, parsed_count, input_path, record, verbose)
            # raise e

        # print profile results
        # pr.disable()
        # s = io.StringIO()
        # ps = pstats.Stats(pr, stream=s).sort_stats(SortKey.CUMULATIVE)
        # ps.print_stats()
        # print(s.getvalue())
        # end = datetime.datetime.now()
        # print("transform elapsed", end - start)

    close_emitters(emitters)

    return TransformationResults(
        parsed_count=parsed_count,
        emitted_count=emitted_count,
        validation_errors=validation_errors,
        transformer_errors=transformer_errors
    )
