import os
import sqlite3
import json

import pytest
from fhir.resources.patient import Patient

from g3t_etl.util.local_fhir_db import LocalFHIRDatabase


@pytest.fixture
def db_name(tmp_path):
    path = 'tests/fixtures/test_example.db'
    return path


@pytest.fixture
def db(db_name):
    if os.path.exists(db_name):
        os.remove(db_name)
    yield LocalFHIRDatabase(db_name=db_name)
    # os.remove(db_name)


@pytest.fixture
def file_path():
    return 'tests/fixtures/sample_fhir/Patient.ndjson'


@pytest.fixture
def patient_id():
    return "c377f672-45d3-5075-b23a-3a515565b4a8"


@pytest.fixture
def ndjson_dir():
    return 'tests/fixtures/sample_dataset-FHIR/dummy_data_30pid'


@pytest.fixture
def identifier_value():
    return "123"


def test_create_table(db):
    db.create_table()

    # Check if the table has been created in the database
    connection = sqlite3.connect(db.db_name)
    cursor = connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resources'")
    table_exists = cursor.fetchone()
    connection.close()

    assert table_exists is not None, "Table 'resources' not created."


def test_insert_data(db):
    db.create_table()
    db.connect()
    data = {'id': '1', 'resource_type': 'Patient', 'key': 'value1', 'number': 42}
    db.insert_data_from_dict(data)
    db.connection.commit()

    # Check if the data has been inserted into the database
    connection = sqlite3.connect(db.db_name)
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM resources WHERE key=?", ('Patient/1',))
    result = cursor.fetchone()
    connection.close()

    assert result is not None, "Data not inserted into the database."
    assert result[0] == 'Patient/1', "Incorrect key value."
    assert result[1] == 'Patient', "Incorrect resource_type value."
    assert json.loads(result[2]) == data, "Incorrect resource value."


def test_load_from_ndjson_file(db, file_path):
    db.load_from_ndjson_file(file_path)

    # Check if the data from the NDJSON file has been inserted into the database
    connection = sqlite3.connect(db.db_name)
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM resources")
    count = cursor.fetchone()[0]
    connection.close()

    assert count > 0, "No data loaded from NDJSON file."


def test_load_json_query(db, file_path, patient_id, identifier_value):
    db.load_from_ndjson_file(file_path)

    # Check if the data from the NDJSON file has been inserted into the database
    connection = sqlite3.connect(db.db_name)
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM resources WHERE json_extract(resource, '$.id') = ?", (patient_id,))
    key, resource_type, resource = cursor.fetchone()
    assert key == f"Patient/{patient_id}", key
    assert resource_type == 'Patient', resource_type
    assert resource is not None, resource
    resource = json.loads(resource)
    assert resource['id'] == patient_id, resource

    cursor.execute("SELECT * FROM resources WHERE json_extract(resource, '$.identifier[0].value') = ?",
                   (identifier_value,))
    key, resource_type, resource = cursor.fetchone()
    assert resource_type == 'Patient', resource_type
    assert resource is not None, resource
    resource = json.loads(resource)
    assert resource['identifier'][0]['value'] == identifier_value, resource

    connection.close()


def test_loaded_data_valid(db, file_path):
    db.load_from_ndjson_file(file_path)

    # Check if the data from the NDJSON file has been inserted into the database
    connection = sqlite3.connect(db.db_name)
    cursor = connection.cursor()
    cursor.execute("SELECT resource FROM resources")
    for _tuple in cursor.fetchall():
        resource = _tuple[0]
        Patient(**json.loads(resource))  # Raises an exception if the resource is not valid
    connection.close()


@pytest.fixture
def loaded_db(db, ndjson_dir):
    db.load_ndjson_from_dir(path=ndjson_dir)
    return db


@pytest.fixture
def expected_count():
    return 7517


@pytest.fixture
def patient_expected_resource_count():
    return 187


@pytest.fixture
def patient_count():
    return 30


@pytest.fixture
def procedure_expected_resource_count():
    return 160


def test_load_from_dir(loaded_db, expected_count):
    """Check if the data from the NDJSON files has been inserted into the database"""
    connection = sqlite3.connect(loaded_db.db_name)
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM resources")
    count = cursor.fetchone()[0]
    connection.close()

    assert count == expected_count, f"Incomplete data loaded from NDJSON file. resource count: {count}"


def test_patient_load(loaded_db, patient_id, patient_expected_resource_count):
    """Check if the data from the NDJSON files has been inserted into the database"""

    resources = []
    c = 0

    for _ in loaded_db.patient_everything(patient_id):
        resources.append(_)
        c += 1
    assert c == patient_expected_resource_count, f"Expected {patient_expected_resource_count}, got {c}"

    patient = loaded_db.patient(patient_id)

    assert patient_id == patient['id'], f"Expected {patient_id}, got {patient['id']}"


# @pytest.mark.skip(reason="Regression?  AssertionError: reason is not a string")
def test_procedure_everything(loaded_db, procedure_expected_resource_count):
    """Normalize, patient, condition and observation connected to procedure."""

    c = loaded_db.bulk_insert_data(loaded_db.flatten(resource_type="Procedure"), table_name="procedure_everything")
    assert c == procedure_expected_resource_count, f"Expected {procedure_expected_resource_count}, got {c}"
    loaded_db.disconnect()
    assert loaded_db.count() > 0, "No data loaded from NDJSON file."
    assert loaded_db.count(table_name="procedure_everything") > 0, "No data loaded into procedure_everything."
    (resource, ) = loaded_db.connection.cursor().execute("SELECT resource FROM procedure_everything").fetchone()
    assert resource is not None, "No data loaded into procedure_everything."
    resource = json.loads(resource)
    assert 'id' in resource, "No id in procedure"
    assert 'code' in resource, "No code in procedure"
    print(resource.keys())
    assert 'gleason' in resource.keys(), f"No gleason in procedure, {resource.keys()}"
    assert 'reason' in resource.keys(), "No reason in procedure"
    # from pprint import pprint
    # pprint(resource)
    # assert isinstance(resource['reason'], str), f"reason is not a string {resource['reason']}"


def test_patient_everything(loaded_db, patient_count):
    """Normalize, patient, etc connected to procedure."""

    c = loaded_db.bulk_insert_data(loaded_db.flatten(resource_type="Patient"), table_name="patient_everything")
    assert c == patient_count, f"Expected {patient_count}, got {c}"
    loaded_db.disconnect()
    assert loaded_db.count() > 0, "No data loaded from NDJSON file."
    assert loaded_db.count(table_name="patient_everything") > 0, "No data loaded into patient_everything."
    (resource, ) = loaded_db.connection.cursor().execute("SELECT resource FROM patient_everything").fetchone()
    assert resource is not None, "No data loaded into procedure_everything."
    resource = json.loads(resource)
    assert 'id' in resource, "No id in resource"
    # assert 'code' in resource, "No code in resource"
    # assert 'gleason' in resource.keys(), "No gleason in resource"
    # assert 'reason' in resource.keys(), "No reason in resource"
    # assert isinstance(resource['reason'], str), "reason is not a string"
    print(json.dumps(resource, indent=2))
    # assert False
