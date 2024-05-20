"""Factory for creating a transformer."""
import pathlib
from typing import Callable

import numpy as np
import pandas
from pydantic import BaseModel, ConfigDict, ValidationError

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
        get_emitter(emitters, research_study.resource_type, str(output_path), verbose=False).write(research_study.json() + "\n")
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
                get_emitter(emitters, resource.resource_type, str(output_path), verbose=False).write(resource.json() + "\n")
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
