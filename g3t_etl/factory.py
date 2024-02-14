"""Factory for creating a game character."""
import logging
import pathlib
from typing import Any, Callable

from typing import Protocol

import numpy as np
import pandas
import yaml
from fhir.resources.condition import Condition
from fhir.resources.identifier import Identifier
from fhir.resources.observation import Observation
from fhir.resources.reference import Reference
from fhir.resources.researchstudy import ResearchStudy
from fhir.resources.resource import Resource
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.fields import FieldInfo
from abc import ABC, abstractmethod

from g3t_etl import TransformerHelper, get_emitter, print_transformation_error, print_validation_error, close_emitters

logger = logging.getLogger(__name__)


with open("templates/ResearchStudy.yaml") as fp:
    RESEARCH_STUDY = yaml.safe_load(fp)

with open("templates/Condition.yaml") as fp:
    CONDITION = yaml.safe_load(fp)

with open("templates/Observation.yaml") as fp:
    OBSERVATION = yaml.safe_load(fp)


_project_id = 'unknown-unknown'
if pathlib.Path('.g3t/config.yaml').exists():
    with open('.g3t/config.yaml') as f:
        config = yaml.safe_load(f)
        _project_id = config['gen3']['project_id']
else:
    logger.warning(f"No .g3t/config.yaml found. See `g3t init` or `g3t clone`.  Proceeding with project_id {_project_id}.")

helper = TransformerHelper(project_id=_project_id)


class Transformer(Protocol):
    """Basic representation of an ETL transformer."""

    def transform(self, research_study: ResearchStudy = None) -> list[Resource]:
        """Transform the input record into FHIR resources."""


transformers: list[Callable[..., Transformer]] = []
default_dictionary_path: None


def default_transformer():
    """Default transformer."""
    return transformers[0]


def register(transformer: Callable[..., Transformer], dictionary_path: str) -> None:
    """Register a new transformer."""
    transformers.append(transformer)
    global default_dictionary_path
    default_dictionary_path = dictionary_path


def unregister(transformer: Callable[..., Transformer]) -> None:
    """Unregister a transformer."""
    transformers.remove(transformer)


def template_condition(subject: Reference) -> Condition:
    """Create a generic prostate cancer condition."""
    CONDITION['subject'] = subject
    return Condition(**CONDITION)


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

    df = pandas.read_csv(input_path)
    df = df.replace({np.nan: None})
    records = df.to_dict(orient='records')

    parsed_count = 0
    emitted_count = 0
    validation_errors = []
    transformer_errors = []

    try:
        research_study = ResearchStudy(**RESEARCH_STUDY)
        identifier = helper.populate_identifier(value=_project_id)
        id_ = helper.mint_id(identifier=identifier, resource_type='ResearchStudy')
        research_study.id = id_
        research_study.identifier = [identifier]
        already_seen.add(research_study.id)
        get_emitter(emitters, research_study.resource_type, str(output_path), verbose=False).write(research_study.json() + "\n")
        emitted_count += 1

    except ValidationError as e:
        transformer_errors.append(e)
        print_transformation_error(e, parsed_count, input_path, RESEARCH_STUDY, verbose)
        raise e

    for record in records:

        try:
            transformer = default_transformer()(**record, helper=helper)
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
            raise e

    close_emitters(emitters)

    return TransformationResults(
        parsed_count=parsed_count,
        emitted_count=emitted_count,
        validation_errors=validation_errors,
        transformer_errors=transformer_errors
    )


def additional_observation_codings(field_info: FieldInfo) -> list[dict]:
    """Additional codings for the observation."""

    if 'code' in field_info.json_schema_extra:
        return [{
            "system": field_info.json_schema_extra['coding_system'],
            "code": field_info.json_schema_extra['coding_code'],
            "display": field_info.json_schema_extra['coding_display']
        }]
    return []


class FHIRTransformer(ABC):
    """Abstract helper class, implementers can combine with a BaseModel of their submission."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize, save passed helper."""
        self._helper = kwargs['helper']

    @abstractmethod
    def transform(self, research_study: ResearchStudy = None) -> list[Resource]:
        """Implementers must implement this method."""
        pass

    def create_observations(self, subject, focus) -> list[Observation]:
        """Create observations."""
        observations = []

        observation_fields = {}
        for field, field_info in self.model_fields.items():  # noqa - implementers must implement this method ie inherit from BaseModel
            if not field_info.json_schema_extra:
                continue
            if 'observation_subject' in field_info.json_schema_extra:
                if field_info.json_schema_extra['observation_subject'] == focus.resource_type:
                    observation_fields[field] = field_info

        # for all attributes in raw record ...
        for field, field_info in observation_fields.items():

            # that are not null ...
            value = getattr(self, field)
            if not value:
                continue

            # and create an observation
            subject_identifier = self._helper.get_official_identifier(subject).value
            focus_identifier = self._helper.get_official_identifier(focus).value
            identifier = self.populate_identifier(value=f"{subject_identifier}-{focus_identifier}-{field}")
            id_ = self.mint_id(identifier=identifier, resource_type='Observation')
            more_codings = additional_observation_codings(field_info)

            if 'code' in OBSERVATION:
                del OBSERVATION['code']
            observation = Observation(
                **OBSERVATION,
                code=self.populate_codeable_concept(code=field, display=field_info.description)
            )
            observation.id = id_
            observation.identifier = [identifier]
            observation.subject = self.to_reference(subject)
            observation.focus = [self.to_reference(focus)]
            if more_codings:
                observation.code.coding.extend(more_codings)  # noqa - unclear? Unresolved attribute reference 'coding' for class 'CodeableConceptType'

            # the annotations are often decorated with Optional, so cast to string and check for the type
            field_type = str(field_info.annotation)
            if 'int' in field_type:
                observation.valueInteger = getattr(self, field)
            elif 'float' in field_type or 'decimal' in field_type or 'number' in field_type:
                observation.valueQuantity = self.to_quantity(field, field_info)
            else:
                observation.valueString = getattr(self, field)

            observations.append(observation)

        return observations

    def to_quantity(self, field, field_info) -> dict:
        """Convert to FHIR Quantity."""
        _ = {
            "value": getattr(self, field),
        }
        if field_info.json_schema_extra:
            if 'uom_system' in field_info.json_schema_extra:
                _['system'] = field_info.json_schema_extra['uom_system']
                _['code'] = field_info.json_schema_extra['uom_code']
                _['unit'] = field_info.json_schema_extra['uom_unit']
        return _

    def mint_id(self, *args: Any, **kwargs: Any) -> str:
        """Create a UUID from an identifier."""
        # dispatch to helper
        return self._helper.mint_id(*args, **kwargs)

    def populate_identifier(self, *args: Any, **kwargs: Any) -> Identifier:
        """Populate a FHIR Identifier."""
        # dispatch to helper
        return self._helper.populate_identifier(*args, **kwargs)

    def to_reference(self, *args: Any, **kwargs: Any) -> Reference:
        """Create a reference from a resource of the form RESOURCE/id."""
        # dispatch to helper
        return self._helper.to_reference(*args, **kwargs)

    def populate_codeable_concept(self, *args: Any, **kwargs: Any) -> dict:
        """Populate a FHIR CodeableConcept."""
        # dispatch to helper
        return self._helper.populate_codeable_concept(*args, **kwargs)

    @classmethod
    def template_condition(cls, *args: Any, **kwargs: Any) -> Condition:
        """Create a generic prostate cancer condition."""
        # dispatch to helper
        return template_condition(*args, **kwargs)
