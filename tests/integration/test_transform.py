import pathlib

from g3t_etl.factory import transform_csv
from g3t_etl.loader import load_plugins


def test_transform_dummy_data(test_fixture_paths, plugins, test_fixture_fhir_path):
    """Transform the dummy data to FHIR, store in test fixture."""
    validation_errors = []
    transformer_errors = []
    emitted_count = 0
    parsed_count = 0
    load_plugins(plugins)

    for input_path in test_fixture_paths:

        output_path = pathlib.Path(test_fixture_fhir_path) / input_path.stem

        output_path.mkdir(parents=True, exist_ok=True)

        assert input_path.exists(), f"File must exist {input_path}"

        results = transform_csv(input_path, output_path)

        parsed_count += results.parsed_count
        emitted_count += results.emitted_count
        validation_errors.extend(results.validation_errors)
        transformer_errors.extend(results.transformer_errors)
        # remove redundant validation, as it will be done in the next step, `g3t commit`
        # validate(config=None, directory_path=output_path)
        break
    print(f"emitted {emitted_count} resources from {parsed_count} input resources")
    assert len(validation_errors) == 0, f"validation_errors errors {transformer_errors}"
    assert len(transformer_errors) == 0, f"transformer_errors errors {transformer_errors}"

    # TODO assert Procedure.reason, Procedure.code and Procedure.occurrenceAge are set
