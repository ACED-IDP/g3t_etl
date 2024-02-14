import numpy as np
import pandas
from pydantic import ValidationError

from g3t_etl import print_validation_error
from sample_transformer.submission import Submission


def test_submission_dictionary(expected_keys):
    """Was the submission model created correctly?"""
    from sample_transformer.submission import Submission
    _ = Submission.schema()
    assert _, "do not have a schema"
    actual_keys = sorted(_['properties'].keys())
    assert actual_keys == expected_keys, "do not have expected keys"


def test_submission_dummy_data(test_fixture_paths):
    """Can we read the dummy data?"""
    for dummy_data_path in test_fixture_paths:
        assert dummy_data_path.exists(), f"do not have {dummy_data_path}"
        df = pandas.read_csv(dummy_data_path)
        df = df.replace({np.nan: None})
        records = df.to_dict(orient='records')
        c = 1
        for record in records:
            try:
                _ = Submission(**record)
                c += 1
            except ValidationError as e:
                print_validation_error(e, c, dummy_data_path, record)
                raise e
