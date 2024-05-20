import logging
import pathlib
import subprocess
import sys
import traceback
import uuid
from collections import defaultdict
from typing import Callable, TextIO, Optional, Any, Protocol

from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.codeablereference import CodeableReference
from fhir.resources.identifier import Identifier
from fhir.resources.reference import Reference
from fhir.resources.researchstudy import ResearchStudy
from fhir.resources.resource import Resource
from gen3_tracker.common import read_ndjson_file
from nested_lookup import nested_lookup
from pydantic import BaseModel, computed_field, ConfigDict, ValidationError, field_validator
from pydantic_core import InitErrorDetails
logger = logging.getLogger(__name__)

IDENTIFIER_USE = 'official'
ACED_NAMESPACE = uuid.uuid3(uuid.NAMESPACE_DNS, 'aced-idp.org')


class IdMinter(BaseModel):
    """Mint identifiers based on namespace and project_id."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_id: str
    """project_id for minting UUIDs, unique within a namespace."""
    namespace_url: str = 'https://aced-idp.org'
    """Default system for identifiers, codeable concepts."""
    namespace: Optional[uuid.UUID] = ACED_NAMESPACE
    """Consortium e.g. ACED, TCGA, etc."""

    @computed_field
    def system(self) -> str:
        """Default system for identifiers, codeable concepts."""
        return f"{self.namespace_url}/{self.project_id}"

    @field_validator('project_id')
    @classmethod
    def check_project_id(cls, project_id: str) -> str:
        """Check project_id."""
        try:
            assert '-' in project_id, f"{project_id} should have a single '-' separating program and project"
            assert project_id.count('-') == 1, f"{project_id} should have a single '-' separating program and project"
            return project_id
        except AssertionError as e:
            raise ValueError(e)

    @field_validator('namespace', mode='before')
    @classmethod
    def xform_namespace(cls, namespace: Any) -> uuid.UUID:
        """Check namespace."""
        try:
            assert namespace, "namespace should not be None"
            return uuid.uuid3(uuid.NAMESPACE_DNS, namespace)
        except AssertionError as e:
            raise ValueError(e)

    def mint_id(self, identifier: Identifier | str, resource_type: str = None) -> str:
        """Create a UUID from an identifier."""
        # dispatch on type
        if isinstance(identifier, Identifier):
            assert resource_type, "resource_type is required for Identifier"
            identifier = f"{resource_type}/{identifier.system}|{identifier.value}"
        return self._mint_id(identifier)

    def _mint_id(self, identifier_string: str) -> str:
        """Create a UUID from an identifier, insert project_id."""
        return str(uuid.uuid5(self.namespace, f"{self.project_id}/{identifier_string}"))


class TransformerHelper(IdMinter):
    """FHIR helper for transformers."""

    def populate_identifier(self, value: str, system: str = None, use: str = IDENTIFIER_USE) -> Identifier:
        """Populate a FHIR Identifier."""
        if not system or 'http' not in system:
            system = self.system
        if not value:
            raise ValidationError.from_exception_data(
                title="value is required for Identifier",
                line_errors=[InitErrorDetails(type='missing', loc=("value",), msg="value is required for Identifier")],
            )
        _ = Identifier(system=system, value=value, use=use)
        return _

    @classmethod
    def get_official_identifier(cls, resource: Resource) -> Identifier:
        """Get the official identifier from a fhir resource."""
        _ = next(iter(_ for _ in resource.identifier if _.use == IDENTIFIER_USE), None)
        assert _, f"Could not find {IDENTIFIER_USE} identifier for {resource}"
        return _

    @classmethod
    def to_reference_identifier(cls, resource: Resource) -> Reference:
        """Create a reference from a resource of the form RESOURCE?identifier=system|value."""
        _ = TransformerHelper.get_official_identifier(resource)
        return Reference(reference=f"{resource.resource_type}?identifier={_.system}|{_.value}")

    @classmethod
    def to_reference(cls, resource: Resource) -> Reference:
        """Create a reference from a resource of the form RESOURCE/id."""
        return Reference(reference=f"{resource.resource_type}/{resource.id}")

    @classmethod
    def to_codeable_reference(cls, resource: Resource = None, concept: CodeableConcept = None) -> Reference:
        """Create a reference from a resource of the form RESOURCE/id."""
        _ = CodeableReference()
        if resource:
            _.reference = Reference(reference=f"{resource.resource_type}/{resource.id}")
        if concept:
            _.concept = concept
        assert _ and (_.reference or _.concept), f"Could not create CodeableReference from {resource} and {concept}"
        return _

    def populate_codeable_concept(self, code: str, display: str, system: str = None, text: str = None) -> CodeableConcept:
        """Populate a FHIR CodeableConcept."""
        if not text:
            text = display
        if not system or 'http' not in system:
            system = self.system
        return CodeableConcept(**{
            'coding': [
                         {
                             'system': system,
                             'code': code,
                             'display': display
                         }
                     ],
            'text': text
        })


def get_emitter(emitters: dict, emitter_name: str, output_path: str, verbose=False, file_mode="w") -> TextIO:
    """Returns emitter by name."""
    emitter = emitters.get(emitter_name, None)
    if not emitter:
        _ = pathlib.Path(output_path) / f"{emitter_name}.ndjson"
        emitter = open(_, file_mode)
        emitters[emitter_name] = emitter
        if verbose:
            logger.info(f"opened {emitter.name}")
    return emitter


def close_emitters(emitters: dict, verbose=False):
    """Close all emitters."""
    for emitter_name, emitter in emitters.items():
        emitter.close()
        if verbose:
            logger.info(f"closed {emitter.name}")


def aggregate(metadata_path: pathlib.Path | str) -> dict:
    """Aggregate metadata counts resourceType(count)-count->resourceType(count)."""

    nested_dict: Callable[[], defaultdict[str, defaultdict]] = lambda: defaultdict(defaultdict)

    if not isinstance(metadata_path, pathlib.Path):
        metadata_path = pathlib.Path(metadata_path)
    summary = nested_dict()
    for path in sorted(metadata_path.glob("*.ndjson")):
        for _ in read_ndjson_file(path):

            resource_type = _['resourceType']
            if 'count' not in summary[resource_type]:
                summary[resource_type]['count'] = 0
            summary[resource_type]['count'] += 1

            refs = nested_lookup('reference', _)
            for ref in refs:
                # A codeable reference is an object with a codeable concept and a reference
                if isinstance(ref, dict):
                    ref = ref['reference']
                ref_resource_type = ref.split('/')[0]
                if 'references' not in summary[resource_type]:
                    summary[resource_type]['references'] = nested_dict()
                dst = summary[resource_type]['references'][ref_resource_type]
                if 'count' not in dst:
                    dst['count'] = 0
                dst['count'] += 1

    return summary


def print_transformation_error(e: ValidationError, index, path, record, verbose: bool = False):
    """Print validation error details.

    Parameters:
    - e (ValidationError): The validation error.
    - index (int): The index of the record.
    - path (str): The path to the file.
    - record (dict): The record that caused the error.
    """
    for error in e.errors():
        error['messages'] = []
        for location in error['loc']:
            if location not in record:
                msg = f"{location} not in record {path} line {index}"
            else:
                msg = f"{path} line {index} value {record[location]}"
            error['messages'].append(msg)
        if verbose:
            tb = traceback.format_exc()
            print(error, tb, file=sys.stderr)


def print_validation_error(e: ValidationError, index, path, record, verbose: bool = False):
    """Print validation error details.

    Parameters:
    - e (ValidationError): The validation error.
    - index (int): The index of the record.
    - path (str): The path to the file.
    - record (dict): The record that caused the error.
    """
    for error in e.errors():
        error['messages'] = []
        for location in error['loc']:
            if location not in record:
                msg = f"{location} not in record {path} line {index}"
            else:
                msg = f"{path} line {index} value {record[location]}"
            error['messages'].append(msg)
        if verbose:
            tb = traceback.format_exc()
            print(error, tb, file=sys.stderr)


class Transformer(Protocol):
    """Basic representation of an ETL transformer."""

    def transform(self, research_study: ResearchStudy = None) -> list[Resource]:
        """Transform the input record into FHIR resources."""


def run_command(cmd: str | list[str]) -> (int, str, str):
    """Run a command. returns returncode, stdout, stderr."""

    if isinstance(cmd, str):
        cmd = cmd.split()

    # Run the command
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Get the output and error
    stdout, stderr = process.communicate()

    return process.returncode, stdout.decode(), stderr.decode()
