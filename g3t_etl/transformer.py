"""Factory for creating a transformer."""
import inspect
import logging
import os
import pathlib
import shutil
import sys
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Callable, ClassVar, NamedTuple

import click
import yaml
from fhir.resources.codeablereference import CodeableReference
from fhir.resources.condition import Condition
from fhir.resources.fhirtypes import CodeableConceptType
from fhir.resources.identifier import Identifier
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient
from fhir.resources.procedure import Procedure
from fhir.resources.reference import Reference
from fhir.resources.researchstudy import ResearchStudy
from fhir.resources.researchsubject import ResearchSubject
from fhir.resources.resource import Resource
from fhir.resources.specimen import Specimen
from jinja2 import Environment, FileSystemLoader, select_autoescape, PackageLoader
from pydantic import ConfigDict
from pydantic.fields import FieldInfo

from g3t_etl import TransformerHelper, Transformer

logger = logging.getLogger(__name__)


# with open("templates/ResearchStudy.yaml") as fp:
#     RESEARCH_STUDY = yaml.safe_load(fp)
#
# # with open("templates/Condition.yaml.jinja") as fp:
# #     CONDITION = yaml.safe_load(fp)
#
# with open("templates/Observation.yaml.jinja") as fp:
#     OBSERVATION = yaml.safe_load(fp)
#
# # with open("templates/Procedure.yaml.jinja") as fp:
# #     PROCEDURE = yaml.safe_load(fp)
#
# with open("templates/Specimen.yaml") as fp:
#     SPECIMEN = yaml.safe_load(fp)
#
# with open("templates/Patient.yaml") as fp:
#     PATIENT = yaml.safe_load(fp)
#
#
# JINJA_ENV = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape())

_project_id = 'unknown-unknown'
if pathlib.Path('.g3t/config.yaml').exists():
    with open('.g3t/config.yaml') as f:
        config = yaml.safe_load(f)
        _project_id = config['gen3']['project_id']
else:
    logger.warning(f"No .g3t/config.yaml found. See `g3t init` or `g3t clone`.  Proceeding with project_id {_project_id}.")

DEFAULT_HELPER = TransformerHelper(project_id=_project_id)


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


# def template_condition(subject: Reference) -> Condition:
#     """Create a generic prostate cancer condition."""
#     CONDITION['subject'] = subject
#     return Condition(**CONDITION)


def template_research_study() -> ResearchStudy:
    research_study = ResearchStudy(**RESEARCH_STUDY)
    identifier = DEFAULT_HELPER.populate_identifier(value=_project_id)
    id_ = DEFAULT_HELPER.mint_id(identifier=identifier, resource_type='ResearchStudy')
    research_study.id = id_
    research_study.identifier = [identifier]
    return research_study


def template_specimen(subject: Reference) -> Procedure:
    """Create a generic specimen."""
    SPECIMEN['subject'] = subject
    return Specimen(**SPECIMEN)


def template_patient() -> Patient:
    """Create a generic patient."""
    return Patient(**PATIENT)


def additional_observation_codings(field_info: FieldInfo) -> list[dict]:
    """Additional codings for the observation."""

    if 'coding_code' in field_info.json_schema_extra:
        return [{
            "system": field_info.json_schema_extra['coding_system'],
            "code": field_info.json_schema_extra['coding_code'],
            "display": field_info.json_schema_extra['coding_display']
        }]
    return []


class FieldMappingInstance(NamedTuple):
    """Field name, info and value"""
    field: str
    field_info: FieldInfo
    value: Any


class FHIRTransformer(ABC):
    """Abstract helper class, implementers can combine with a BaseModel of their submission."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra='allow')
    """Allow arbitrary types. e.g. dicts"""

    _logged_already: ClassVar[list] = []
    """Class variable to log mappings once."""
    _mapped_fields: dict[str, FieldInfo] = {}
    """Fields that have been mapped to FHIR resources."""
    _unmapped_fields: dict[str, FieldInfo] = {}
    """Fields that have not been mapped to FHIR resources."""
    _resource_mapping: dict[str, dict[str, FieldMappingInstance]] = {}
    """mapped fields by resource_type."""
    _observation_mapping: list[FieldMappingInstance] = []
    """mapped associations for observations."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize, save passed helper."""
        self._helper = kwargs.get('helper', None)

        self._mapped_fields = {k: v for k, v in self.model_fields.items() if
                               v.json_schema_extra and 'fhir_resource_type' in v.json_schema_extra}

        for k, v in self.model_computed_fields.items():
            if v.json_schema_extra and 'fhir_resource_type' in v.json_schema_extra:
                self._mapped_fields[k] = v

        self._unmapped_fields = {k: v for k, v in self.model_fields.items() if
                                 v.json_schema_extra and 'fhir_resource_type' not in v.json_schema_extra}
        if 'field_mappings' not in self.logged_already:
            logger.info(f"Unmapped fields {self._unmapped_fields}")
            logger.info(f"Mapped fields {self._mapped_fields}")
            self.logged_already.append('field_mappings')

        self._resource_mapping = defaultdict(dict)
        self._observation_mapping = []
        for k, v in self.mapped_fields.items():
            if not hasattr(self, k):
                continue
            resource_type = v.json_schema_extra['fhir_resource_type']
            # only mappings with properties
            if '.' in resource_type:
                resource_type, _ = resource_type.split('.', maxsplit=1)
                self._resource_mapping[resource_type][_] = FieldMappingInstance(**{'field_info': v, 'field': k, 'value': getattr(self, k)})
            elif resource_type == 'Observation':
                self._observation_mapping.append(FieldMappingInstance(**{'field_info': v, 'field': k, 'value': getattr(self, k)}))
            else:
                assert False, f"unknown mapping {(k, v)}"

    @property
    def logged_already(self) -> list:
        """Class variableReturn the logged already."""
        return FHIRTransformer._logged_already

    @property
    def mapped_fields(self) -> dict[str, FieldInfo]:
        """Return the mapped fields."""
        return self._mapped_fields

    @property
    def unmapped_fields(self) -> dict[str, FieldInfo]:
        """Return the unmapped fields."""
        return self._unmapped_fields

    @property
    def observation_mapping(self) -> list[FieldMappingInstance]:
        """Return the observation mappings."""
        return self._observation_mapping

    @abstractmethod
    def transform(self, research_study: ResearchStudy = None) -> list[Resource]:
        """Implementers must implement this method."""
        pass

    @property
    def resource_mapping(self) -> dict[str, dict[str, Any]]:
        """Utility method, create a dict, of mapped properties for each resource_type."""
        return self._resource_mapping

    def create_research_study(self) -> ResearchStudy:
        """Create a research study."""
        return template_research_study()

    def create_patient(self, generated_resources: list[Resource]) -> Patient | None:
        """Create a patient."""
        if 'Patient' not in self.resource_mapping:
            return None

        patient_mapping = self.resource_mapping['Patient']
        assert 'identifier' in patient_mapping, f"Patient must have an identifier {self}"
        identifier = self.populate_identifier(value=patient_mapping['identifier'].value)
        patient = self.template_patient()
        patient.id = self.mint_id(identifier=identifier, resource_type='Patient')
        patient.identifier = [identifier]

        for field, info in patient_mapping.items():
            if field == 'identifier':
                # already processed this
                continue
            setattr(patient, field, info['value'])

        return patient

    def create_specimen(self, patient: Patient | None, generated_resources: list[Resource]) -> Specimen | None:
        """Create a specimen."""
        if 'Specimen' not in self.resource_mapping:
            return None

        specimen_mapping = self.resource_mapping['Specimen']
        assert 'identifier' in specimen_mapping, f"Specimen must have an identifier {self}"
        identifier = self.populate_identifier(value=specimen_mapping['identifier'].value)
        assert patient, f"Patient must be created before Specimen {self}"
        specimen = self.template_specimen(subject=self.to_reference(patient))
        specimen.identifier = [identifier]
        specimen.id = self.mint_id(identifier=identifier, resource_type='Patient')
        for field, info in specimen_mapping.items():
            if field == 'identifier':
                # already processed this
                continue
            field_root = field.split('.')[0].split('[')[0]
            if not hasattr(specimen, field_root):
                logger.warning(f"Specimen has no field {field} {info['value']}")
                continue
            try:
                value = info.value
                # TODO - there should be a more elegant way to do this
                # TODO for now, let's maintain these nested fields manually :-(  - need to use templates
                if 'collection.bodySite' == field:
                    specimen.collection.bodySite = self.to_codeable_reference(concept=self.populate_codeable_concept(code=value, display=value))
                    continue
                if 'processing[0].method' == field:
                    specimen.processing[0].method = self.populate_codeable_concept(code=value, display=value)
                    continue

                if specimen.__fields__[field].outer_type_ == CodeableConceptType:
                    value = self.populate_codeable_concept(code=value, display=value)

                setattr(specimen, field, value)

            except Exception as e:
                logger.error(f"Error setting field {field} to {info.value}: {e}")
                raise e

        return specimen

    def create_condition(self, patient: Patient | None, generated_resources: list[Resource]) -> Condition | None:
        """Create a condition."""
        if 'Condition' not in self.resource_mapping:
            return None

        condition_mapping = self.resource_mapping['Condition']

        condition = self.template_condition(subject=patient)

        assert 'identifier' in condition_mapping, f"Condition must have an identifier {self}"
        identifier = condition_mapping['identifier'].value

        condition.identifier = [identifier]
        condition.id = self.mint_id(identifier=identifier, resource_type='Condition')

        # TODO - There is a bit of confusion / duplication here - who is responsible for setting the properties? template, transformer, both?
        for field, info in condition_mapping.items():
            if field in ['code', 'identifier']:
                # already processed these
                continue
            if not hasattr(condition, field):
                # already processed this
                if f'condition_{field}' not in self.logged_already:
                    logger.warning(f'"Condition" object has no field "{field}"')
                    self.logged_already.append(f'condition_{field}')

                continue
            setattr(condition, field, info.value)

        return condition

    def create_procedure(self, patient: Patient | None, generated_resources: list[Resource]) -> Procedure | None:
        """Create a procedure."""
        if 'Procedure' not in self.resource_mapping:
            return None

        procedure_mapping = self.resource_mapping['Procedure']
        assert 'code' in procedure_mapping, f"Procedure must have a code {self}"
        if 'identifier' not in procedure_mapping:
            if 'procedure_identifier' not in self.logged_already:
                logger.warning(f"Procedure SHOULD have an identifier {self}, creating from patient identifier")
                self.logged_already.append('procedure_identifier')
            identifier = self.populate_identifier(value=patient.identifier[0].value + '/Procedure/' + procedure_mapping['code'].value)
        else:
            identifier = self.populate_identifier(value=procedure_mapping['identifier'].value)

        procedure = self.template_procedure(subject=self.to_reference(patient))
        procedure.code = procedure_mapping['code'].value
        procedure.identifier = [identifier]
        procedure.id = self.mint_id(identifier=identifier, resource_type='Procedure')
        procedure.subject = self.to_reference(patient)

        # TODO remove, the template should be responsible for this
        # for field, info in procedure_mapping.items():
        #     if field in ['code', 'identifier']:
        #         # already processed this
        #         continue
        #     setattr(procedure, field, info.value)

        for _ in generated_resources:
            if _.resource_type == 'Condition':
                procedure.reason = [self.to_codeable_reference(resource=_)]
                break
        return procedure

    def create_research_subject(self, patient: Patient, research_study: ResearchStudy) -> ResearchSubject:
        """Create research subject."""
        identifier = self.populate_identifier(value=patient.identifier[0].value)
        research_subject = ResearchSubject(
            id=self.mint_id(identifier=identifier, resource_type='ResearchSubject'),
            identifier=[identifier],
            status="active",
            study={'reference': f"ResearchStudy/{research_study.id}"},
            subject={'reference': f"Patient/{patient.id}"}
        )
        return research_subject

    def default_transform(self, research_study: ResearchStudy) -> list[Resource]:
        """Default transformation, call this method if you don't want to implement your own transform."""

        # "process" mappings

        generated_resources: list[Resource] = [research_study]

        patient = self.create_patient(generated_resources)
        if patient:
            research_subject = self.create_research_subject(patient, research_study)
            generated_resources.extend([patient, research_subject])

        specimen = self.create_specimen(patient, generated_resources)
        if specimen:
            generated_resources.append(specimen)

        condition = self.create_condition(patient, generated_resources)
        if condition:
            generated_resources.append(condition)

        procedure = self.create_procedure(patient, generated_resources)
        if procedure:
            generated_resources.append(procedure)

        for _ in generated_resources:
            observations = self.create_observations(subject=patient, focus=_)
            if observations:
                generated_resources.extend(observations)

        return generated_resources

    def create_observations(self, subject, focus) -> list[Observation]:
        """Create observations."""
        observations = []

        # TODO - we already have self.observation_mapping, so we can use that?
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
            identifier = self.observation_identifier(field, focus, subject)
            id_ = self.mint_id(identifier=identifier, resource_type='Observation')
            more_codings = additional_observation_codings(field_info)

            if 'code' in OBSERVATION:
                del OBSERVATION['code']
            code = field
            display = field_info.description
            if not display:
                display = value
            observation = Observation(
                **OBSERVATION,
                code=self.populate_codeable_concept(code=code, display=display)
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
                observation.valueQuantity = self.to_quantity(field=field, field_info=field_info)
            else:
                observation.valueString = getattr(self, field)

            observations.append(observation)

        return observations

    def observation_identifier(self, field, focus, subject):
        subject_identifier = self._helper.get_official_identifier(subject).value
        focus_identifier = self._helper.get_official_identifier(focus).value
        identifier = self.populate_identifier(value=f"{subject_identifier}-{focus_identifier}-{field}")
        return identifier

    def to_quantity(self, field_info: FieldInfo, field=None, value=None) -> dict:
        """Convert to FHIR Quantity."""
        if not value:
            value = getattr(self, field)

        _ = {
            "value": value,
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

    def to_codeable_reference(self, *args: Any, **kwargs: Any) -> CodeableReference:
        """Create a reference from a resource of the form RESOURCE/id."""
        # dispatch to helper
        return self._helper.to_codeable_reference(*args, **kwargs)

    def populate_codeable_concept(self, *args: Any, **kwargs: Any) -> dict:
        """Populate a FHIR CodeableConcept."""
        # dispatch to helper
        return self._helper.populate_codeable_concept(*args, **kwargs)

    def template_condition(self, subject: Patient) -> Condition:
        """Create a generic condition."""
        # dispatch to jinja
        template = JINJA_ENV.get_template("Condition.yaml.jinja")
        _ = template.render(**{'transformer': self})
        condition_dict = yaml.safe_load(_)
        return Condition(**condition_dict, subject=self.to_reference(subject))

    def template_procedure(self, subject: Patient) -> Procedure:
        """Create a generic procedure."""
        # dispatch to helper
        # dispatch to jinja
        template = JINJA_ENV.get_template("Procedure.yaml.jinja")
        _ = template.render(**{'transformer': self})
        procedure_dict = yaml.safe_load(_)
        return Procedure(**procedure_dict, subject=self.to_reference(subject))

    @classmethod
    def template_specimen(cls, *args: Any, **kwargs: Any) -> Procedure:
        """Create a generic specimen."""
        # dispatch to helper
        return template_specimen(*args, **kwargs)

    @classmethod
    def template_patient(cls, *args: Any, **kwargs: Any) -> Procedure:
        """Create a generic patient."""
        # dispatch to helper
        return template_patient(*args, **kwargs)

    @classmethod
    def generate_templates(cls, overwrite: bool = False) -> None:
        """Generate templates."""
        plugin_path = pathlib.Path(os.path.dirname(inspect.getfile(cls)))
        target_template_dir = plugin_path / 'templates'
        target_template_dir.parent.mkdir(parents=True, exist_ok=True)

        reference_templates = Environment(loader=PackageLoader('g3t_etl'), autoescape=select_autoescape())
        reference_observation_template = None
        for _ in reference_templates.list_templates():
            src_template_path = pathlib.Path(reference_templates.get_template(_).filename)
            target_template_path = target_template_dir / src_template_path.name
            if src_template_path.name == 'Observation.yaml.jinja':
                reference_observation_template = src_template_path
            if not overwrite and target_template_path.exists():
                click.secho(f"Skipping existing {target_template_path} (see --overwrite).", fg='yellow', file=sys.stderr)
            else:
                shutil.copy(src_template_path, target_template_path)
                click.secho(f"Created {target_template_path}", fg='green', file=sys.stderr)
        transformer = cls()
        for _ in transformer.observation_mapping:
            target_template_path = target_template_dir / f"Observation-{_.field}.yaml.jinja"
            if not overwrite and target_template_path.exists():
                click.secho(f"Skipping existing {target_template_path} (see --overwrite).", fg='yellow', file=sys.stderr)
            else:
                # the annotations are often decorated with Optional, so cast to string and check for the type
                field_type = str(_.field_info.annotation)
                value_x = None
                if 'int' in field_type:
                    value_x = "valueInteger: {{ " + f"transformer.{_.field}" + " }}"
                elif 'float' in field_type or 'decimal' in field_type or 'number' in field_type:
                    vq = transformer.to_quantity(field=_.field, field_info=_.field_info)
                    vq['value'] = "{{ " + f"transformer.{_.field}" + " }}"
                    if 'system' in vq:
                        value_x = """
valueQuantity:
  value: VALUE
  system: SYSTEM
  code: CODE
  unit: UNIT
                        """.replace('SYSTEM', vq['system']) \
                            .replace('CODE', vq['code']) \
                            .replace('UNIT', vq['unit']) \
                            .replace('VALUE', vq['value']) \
                            .replace('\n', '', 1)

                    else:
                        value_x = """
valueQuantity:
  value: VALUE
                          """.replace('VALUE', vq['value']) \
                            .replace('\n', '', 1)
                else:
                    value_x = "valueString: {{ " + f"transformer.{_.field}" + " }}"

                observation_template = reference_templates.get_template('Observation.yaml.jinja').render(value_x=value_x)
                with open(target_template_path, 'w') as fp:
                    fp.write(observation_template)
                click.secho(f"Created {target_template_path}", fg='green', file=sys.stderr)
