from g3t_etl.submission_dictionary import spreadsheet_json_schema


def test_spreadsheet_json_schema(data_dictionary_input_path, expected_keys):
    """Ensure we can create jsonschema from spreadsheet."""
    schema = spreadsheet_json_schema(data_dictionary_input_path)
    assert schema, f"should have loaded {data_dictionary_input_path}"
    assert 'title' in schema, f"should have title in {schema}"
    assert 'properties' in schema, f"should have properties in {schema}"
    assert '$id' in schema, f"should have id in {schema}"
    expected_id = "https://aced-idp.org/test-sample_transformer/submission.schema.json"
    assert schema['$id'] == expected_id, f"should have id in {schema}"
    actual_keys = sorted(schema['properties'].keys())
    print(actual_keys)
    assert actual_keys == expected_keys, "did not find expected keys"
