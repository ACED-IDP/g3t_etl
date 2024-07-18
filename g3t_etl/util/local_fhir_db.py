import pathlib
import sqlite3
import json
from typing import Generator, Any

import inflection
import ndjson


def is_related_observation(resource, related_resource):
    """Check if the related resource is an observation linked to the resource."""
    observation_links = [_['reference'] for _ in related_resource['focus']]
    observation_links.extend([related_resource['subject']['reference']])
    resource_type = resource['resourceType']
    if f"{resource_type}/{resource['id']}" not in observation_links:
        return False
    return True


def observation_value(related_resource) -> tuple[str, Any]:
    """Return the code  and value of the observation."""
    # TODO - pick first coding, h2 allow user to specify preferred coding
    code = related_resource['code']['coding'][0]['code']
    if 'valueQuantity' in related_resource:
        value = related_resource['valueQuantity']['value']
    elif 'valueCodeableConcept' in related_resource:
        value = related_resource['valueCodeableConcept']['text']
    elif 'valueInteger' in related_resource:
        value = related_resource['valueInteger']
    elif 'valueString' in related_resource:
        value = related_resource['valueString']
    else:
        value = None
    assert value is not None, f"no value for {related_resource['id']}"
    return code, value


def only_scalars(resource: dict) -> dict:
    """Return only the scalar values from the resource."""
    resource_type = resource['resourceType']
    resource_type = inflection.underscore(resource_type)
    skip = ['id', 'resource_type', 'resourceType']
    _ = {f"{resource_type}_{k}": v for k, v in resource.items() if not isinstance(v, (dict, list)) and k not in skip}
    if 'identifier' in resource:
        if isinstance(resource['identifier'], list):
            identifier = resource['identifier'][0]
        else:
            identifier = resource['identifier']
        if isinstance(identifier, dict):
            _['identifier'] = identifier['value']
        else:
            _['identifier'] = identifier
    return _


def simplify_patient(patient: dict) -> dict[str, Any]:
    return only_scalars(patient)


def simplify_condition(condition: dict) -> dict[str, Any]:
    _ = only_scalars(condition)
    _['condition_code'] = condition['code']['text']
    if 'onsetAge' in condition:
        _['condition_onsetAge'] = condition['onsetAge']['value']
    return _


def simplify_procedure(procedure) -> dict[str, Any]:
    _ = only_scalars(procedure)
    _.update({
        'procedure_code': procedure['code']['coding'][0]['display'],
        # 'procedure_reason': procedure['reason'][0]['reference']['reference'],
        # 'procedure_occurrenceAge': procedure['occurrenceAge']['value']
    })
    return _


def simplify_related_resource(resource, related_resource, skipped=['ResearchSubject']) -> dict[str, Any]:
    """Simplify the related resource, returns a dict to apply to resource.

    resource: is the fhir object that is being simplified, not modified in this call
    related_resource: is the fhir object that is related to resource
    returns a dict of the simplified related resource
    """
    simplified = {}
    skipped.append(resource['resourceType'])

    if related_resource['resourceType'] == 'Patient':
        simplified.update(simplify_patient(related_resource))

    elif related_resource['resourceType'] == 'Procedure':
        simplified.update(simplify_procedure(related_resource))

    elif related_resource['resourceType'] == 'Condition':
        if f"Condition/{related_resource['id']}" == resource.get('reason', None):
            simplified.update(simplify_condition(related_resource))
        if related_resource['subject']['reference'] == f"{resource['resourceType']}/{resource['id']}":
            simplified.update(simplify_condition(related_resource))

    elif related_resource['resourceType'] == 'Observation':
        if is_related_observation(resource, related_resource):
            code, value = observation_value(related_resource)
            simplified[code] = value

    # skip these
    elif related_resource['resourceType'] not in skipped:
        # un-anticipated resource type
        assert False, f"Unexpected resource type {related_resource['resourceType']}"

    return simplified


class LocalFHIRDatabase:
    """Local FHIR Database.  This is a simple wrapper around sqlite3 to store FHIR resources.  It is used to store FHIR data"""
    def __init__(self, db_name):  # , db_name=pathlib.Path('.g3t') / 'local.db'):
        self.db_name = db_name
        self.connection = None
        self.cursor = None
        self.table_created = {}  # Flag to track if the table has been created

    def connect(self) -> sqlite3.Cursor:
        self.connection = sqlite3.connect(self.db_name)
        self.cursor = self.connection.cursor()

    def disconnect(self):
        if self.connection:
            self.connection.commit()
            self.connection.close()

    def create_table(
            self,
            name='resources',
            ddl='''
                    CREATE TABLE __NAME__ (
                        key TEXT PRIMARY KEY,
                        resource_type TEXT,
                        resource JSON
                    )
                '''):
        self.connect()
        # Check if the table exists before creating it
        self.cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{name}'")
        table_exists = self.cursor.fetchone()

        if not table_exists:
            ddl = ddl.replace('__NAME__', name)
            self.cursor.execute(ddl)
            self.table_created[name] = True

    def count(self, table_name='resources'):
        self.connect()
        self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = self.cursor.fetchone()[0]
        return count

    def insert_data(self, id_, resource_type, resource, table_name='resources'):
        """Insert data into the database."""
        if table_name not in self.table_created:
            self.create_table(table_name)  # Lazily create the table if not already created

        composite_key = f"{resource_type}/{id_}"
        self.cursor.execute(f'''
            INSERT INTO {table_name} (key, resource_type, resource)
            VALUES (?, ?, ?)
        ''', (composite_key, resource_type, json.dumps(resource)))
        # print(f"Inserted {composite_key} into the database")

    def insert_data_from_dict(self, resource, table_name='resources'):
        """Insert data into the database from a dictionary."""
        if 'id' not in resource or ('resource_type' not in resource and 'resourceType' not in resource):
            raise ValueError(f"Resource dictionary must contain 'id' and 'resource_type' keys {resource}")
        self.insert_data(
            resource['id'],
            resource.get('resource_type', resource.get('resourceType')),
            resource,
            table_name
        )

    def bulk_insert_data(self, resources, table_name='resources') -> int:
        """Bulk insert data into the database."""

        if table_name not in self.table_created:
            self.create_table(table_name)  # Lazily create the table if not already created

        def _prepare(resource):
            resource_type = resource.get('resource_type', resource.get('resourceType'))
            id_ = resource['id']
            composite_key = f"{resource_type}/{id_}"
            return (
                composite_key,
                resource_type,
                json.dumps(resource)
            )

        def _iterate(_resources):
            for _ in _resources:
                yield _prepare(_)

        try:
            self.connect()
            sql = f'''
                INSERT INTO {table_name} (key, resource_type, resource)
                VALUES (?, ?, ?)
            '''
            new_cursor = self.cursor.executemany(sql, _iterate(_resources=resources))

        finally:
            self.connection.commit()
            # self.disconnect()

        return new_cursor.rowcount

    def load_from_ndjson_file(self, file_path, table_name='resources'):
        """Load the NDJSON file into the database."""

        if table_name not in self.table_created:
            self.create_table(table_name)  # Lazily create the table if not already created

        with open(file_path, 'r') as file:
            reader = ndjson.reader(file)
            self.bulk_insert_data(reader)

    def load_ndjson_from_dir(self, path: str = 'META', pattern: str = '*.ndjson'):
        """Load all the NDJSON files in the directory into the database."""
        for file_path in pathlib.Path(path).glob(pattern):
            self.load_from_ndjson_file(file_path)

    def patient_everything(self, patient_id) -> Generator[dict, None, None]:
        """Return all the resources for a patient."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM resources WHERE json_extract(resource, '$.subject.reference') = ?",
                       (f"Patient/{patient_id}",))

        for _ in cursor.fetchall():
            key, resource_type, resource = _
            yield json.loads(resource)

    def patient(self, patient_id) -> dict:
        """Return the patient resource."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM resources WHERE json_extract(resource, '$.id') = ?", (patient_id,))
        key, resource_type, resource = cursor.fetchone()
        return json.loads(resource)

    def flatten(self, resource_type: str) -> Generator[dict, None, None]:
        """Return all resources of type resource_type, flattened with relationships resolved"""
        loaded_db = self
        cursor = self.connection.cursor()
        cursor.execute("SELECT key, resource_type, resource FROM resources where resource_type = ?", (resource_type,))

        for _ in cursor.fetchall():
            key, resource_type, resource = _
            resource = json.loads(resource)
            # simplify the identifier
            resource['identifier'] = resource['identifier'][0]['value']

            if resource_type == 'Procedure':
                for k, v in simplify_procedure(resource).items():
                    resource[k] = v

            # simplify the subject
            subject = None
            if 'subject' in resource:
                subject = resource['subject']['reference']
                resource['subject'] = subject

            if resource_type == 'Patient':
                subject = f"Patient/{resource['id']}"

            if subject and subject.startswith('Patient/'):

                _, patient_id = subject.split('/')
                resources = [_ for _ in loaded_db.patient_everything(patient_id)]
                resources.append(loaded_db.patient(patient_id))

                for related_resource in resources:
                    for k, v in simplify_related_resource(resource, related_resource).items():
                        resource[k] = v

            yield resource
