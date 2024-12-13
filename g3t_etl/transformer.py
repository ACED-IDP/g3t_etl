"""Factory for creating a transformer."""
import inspect
import logging
import os
import orjson
import pathlib
import shutil
import sys
import sqlite3
import pandas as pd
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, ClassVar, NamedTuple, Optional

import click
import inflection
import yaml
from fhir.resources.codeablereference import CodeableReference
from fhir.resources.condition import Condition
from fhir.resources.fhirtypes import CodeableConceptType
from fhir.resources.identifier import Identifier
from fhir.resources.observation import Observation, ObservationComponent
from fhir.resources.patient import Patient
from fhir.resources.group import Group, GroupMember
from fhir.resources.practitioner import Practitioner
from fhir.resources.organization import Organization
from fhir.resources.procedure import Procedure
from fhir.resources.reference import Reference
from fhir.resources.researchstudy import ResearchStudy
from fhir.resources.researchsubject import ResearchSubject
from fhir.resources.resource import Resource
from fhir.resources.specimen import Specimen, SpecimenCollection
from fhir.resources.substance import Substance
from fhir.resources.substancedefinition import SubstanceDefinition, SubstanceDefinitionStructure, \
    SubstanceDefinitionStructureRepresentation, SubstanceDefinitionName
from fhir.resources.medication import Medication, MedicationIngredient
from fhir.resources.medicationadministration import MedicationAdministration, MedicationAdministrationDosage
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.annotation import Annotation
from fhir.resources.timing import Timing, TimingRepeat
from fhir.resources.range import Range
from fhir.resources.quantity import Quantity
from fhir.resources import get_fhir_model_class
from jinja2 import Environment, FileSystemLoader, select_autoescape, PackageLoader
from pydantic import ConfigDict
from pydantic.fields import FieldInfo
from pydantic import BaseModel

from g3t_etl import TransformerHelper, Transformer

logger = logging.getLogger(__name__)
CHEMBL_DB_PATH = "/Users/sanati/KCRB/g3t_etl/resources/chembl/chembl_34.db"


class TemplateHelper:
    """Helper class for templates. Loads default templates and jinja environment."""

    def __init__(self, template_dir: pathlib.Path):
        self.template_dir: pathlib.Path = template_dir
        self.jinja_env: Environment = Environment(loader=FileSystemLoader(self.template_dir),
                                                  autoescape=select_autoescape())
        logger.info(f"Loaded {len(self.jinja_env.list_templates())} templates from {self.template_dir}")

    def render_template(self, template_name: str, transformer: 'FHIRTransformer') -> dict:
        """Render a template, populated with transformer's values."""
        # load the jinja template
        template = self.jinja_env.get_template(template_name)
        assert template, f"Template {template_name} not found in {self.template_dir}"

        # render the template with values from transformer
        rendered = yaml.safe_load(template.render(**{'transformer': transformer}))

        return rendered


_project_id = 'unknown-unknown'
if pathlib.Path('.g3t/config.yaml').exists():
    with open('.g3t/config.yaml') as f:
        config = yaml.safe_load(f)
        _project_id = config['gen3']['project_id']
else:
    if 'G3T_PROJECT_ID' not in os.environ:
        logger.warning(
            f"No .g3t/config.yaml found. See `g3t init` or `g3t clone`.  Proceeding with project_id {_project_id}.")
    else:
        _project_id = os.environ['G3T_PROJECT_ID']

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


class FHIRTransformer(BaseModel):
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
    _helper: TransformerHelper = DEFAULT_HELPER
    """Useful fhir utilities"""
    _template_helper: TemplateHelper = None
    """Transform templates"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize, save passed helper."""
        # must be done first
        super().__init__(**kwargs)

        # helper is a class that provides utility functions for creating FHIR resources
        self._helper: TransformerHelper = kwargs.get('helper', DEFAULT_HELPER)
        assert self._helper, f"helper should be set"

        # template_helper is a class that provides utility functions for creating JINJA templates
        self._template_helper = kwargs.get('template_helper', None)
        assert self._template_helper, f"template_helper should be set"

        # look into the generated class and find the fields that are mapped to FHIR resources
        self._mapped_fields = {k: v for k, v in self.model_fields.items() if
                               v.json_schema_extra and 'fhir_resource_type' in v.json_schema_extra}

        # see if there are any computed fields that are mapped to FHIR resources
        for k, v in self.model_computed_fields.items():
            if v.json_schema_extra and 'fhir_resource_type' in v.json_schema_extra:
                self._mapped_fields[k] = v

        # see if there are fields that are not mapped to FHIR resources
        self._unmapped_fields = {k: v for k, v in self.model_fields.items() if
                                 v.json_schema_extra and 'fhir_resource_type' not in v.json_schema_extra}

        # inform the log about the mappings
        if 'field_mappings' not in self.logged_already:
            logger.info(f"Unmapped fields {self._unmapped_fields}")
            logger.info(f"Mapped fields {self._mapped_fields}")
            self.logged_already.append('field_mappings')

        # look for Observation mappings
        self._resource_mapping = defaultdict(dict)
        self._observation_mapping = []
        for k, v in self.mapped_fields.items():
            if not hasattr(self, k):
                continue
            resource_type = v.json_schema_extra['fhir_resource_type']
            # only mappings with properties
            if '.' in resource_type:
                resource_type, _ = resource_type.split('.', maxsplit=1)
                if resource_type == 'Observation':
                    self._observation_mapping.append(
                        FieldMappingInstance(**{'field_info': v, 'field': k, 'value': getattr(self, k)}))
                else:
                    self._resource_mapping[resource_type][_] = FieldMappingInstance(
                        **{'field_info': v, 'field': k, 'value': getattr(self, k)})
            elif resource_type == 'Observation':
                self._observation_mapping.append(
                    FieldMappingInstance(**{'field_info': v, 'field': k, 'value': getattr(self, k)}))
            else:
                assert False, f"unknown mapping {(k, v)}"
        # print(f"FHIRTransformer init id: {id(self)}",  f"_helper:{self._helper}", f"_template_helper: {self._template_helper}")
        self.SYSTEM_SNOME = 'http://snomed.info/sct'
        self.SYSTEM_LOINC = 'http://loinc.org'
        self.SYSTEM_chEMBL = 'https://www.ebi.ac.uk/chembl'

    def render_template(self, template_name: str) -> dict:
        """Render a template, populated with transformer's values."""
        # dispatch to template_helper
        return self._template_helper.render_template(template_name, self)

    def template_research_study(self) -> ResearchStudy:
        """Create a research study from JINA template."""
        # load the jina template
        research_study_dict = self.render_template("ResearchStudy.yaml.jinja")

        # create the research study
        research_study = ResearchStudy(**research_study_dict)

        # enhance attributes
        identifier = DEFAULT_HELPER.populate_identifier(value=_project_id)
        id_ = DEFAULT_HELPER.mint_id(identifier=identifier, resource_type='ResearchStudy')
        research_study.id = id_
        research_study.identifier = [identifier]

        return research_study

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
        return self.template_research_study()

    def create_practioner(self, generated_resources: list[Resource]) -> Practitioner | None:
        """Create a patient."""
        if 'Practitioner' not in self.resource_mapping:
            return None

        practioner_mapping = self.resource_mapping['Practitioner']
        assert 'identifier' in practioner_mapping, f"Practitioner must have an identifier {self}"
        identifier = self.populate_identifier(value=practioner_mapping['identifier'].value)
        practitioner = self.template_practitioner()
        practitioner.id = self.mint_id(identifier=identifier, resource_type='Practitioner')
        practitioner.identifier = [identifier]

        for field, info in practioner_mapping.items():
            if field == 'identifier':
                # already processed this
                continue
            setattr(practitioner, field, info['value'])

        return practitioner

    def create_organization(self, generated_resources: list[Resource]) -> Organization | None:
        """Create a FHIR organization."""
        if 'Organization' not in self.resource_mapping:
            return None

        organization_mapping = self.resource_mapping['Organization']
        assert 'identifier' in organization_mapping, f"Organization must have an identifier {self}"

        _identifier_value = organization_mapping['identifier'].value

        if hasattr(_identifier_value, 'value') and _identifier_value.value:
            _identifier_value = _identifier_value.value
        elif not isinstance(_identifier_value, str):
            return None

        _part_of = None
        program_organization = None
        if organization_mapping['partOf'].value:
            program_identifier = self.populate_identifier(value=organization_mapping['partOf'].value)
            program_id = self.mint_id(identifier=program_identifier, resource_type='Organization')
            # print(f"capturing part of {organization_mapping['partOf'].value}")
            _part_of = Reference(**{"reference": f"Organization/{program_id}"})

            program_organization = Organization(**{"id": program_id,
                                                   "identifier": [program_identifier],
                                                   "partOf": None})  # requires a lot of code change to return lits[Organization]

        identifier = self.populate_identifier(value=_identifier_value)
        organization = Organization(**{"id": self.mint_id(identifier=identifier, resource_type='Organization'),
                                       "identifier": [identifier],
                                       "partOf": _part_of})

        for field, info in organization_mapping.items():
            if field == 'identifier' or field == 'partOf':
                # already processed this
                continue
            setattr(organization, field, info['value'])

        return organization

    def create_patient(self, generated_resources: list[Resource]) -> Patient | Group | None:
        """Create a patient."""
        if 'Patient' not in self.resource_mapping:
            return None

        patient_mapping = self.resource_mapping['Patient']
        assert 'identifier' in patient_mapping, f"Patient must have an identifier {self}"

        if "," in patient_mapping['identifier'].value:
            patient_identifier_values = patient_mapping['identifier'].value.split(',')
            patient_identifier_values = [x.strip() for x in patient_identifier_values]
            patient_identifier_values.sort()

            members = []
            for group_member_identifier in patient_identifier_values:
                _gp_ident = self.populate_identifier(value=group_member_identifier)
                patient_group_member = self.template_patient()
                patient_group_member.id = self.mint_id(identifier=_gp_ident,
                                                       resource_type='Patient')  # we assume we only have patient groups atm
                patient_group_member.identifier = [_gp_ident]
                # self.create_patient([patient_group_member]) # create the patient in group
                members.append(
                    GroupMember(**{'entity': Reference(**{"reference": f"Patient/{patient_group_member.id}"})}))

            # order of comma seperated values may change the mint id
            # sort the identifiers
            group_identifier = self.populate_identifier(value=','.join(patient_identifier_values))
            group_id = self.mint_id(identifier=group_identifier, resource_type='Group')
            group = Group(**{'id': group_id, "identifier": [group_identifier], "membership": 'definitional',
                             'member': members, "type": "person"})
            return group

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

    def create_specimen(self, patient: Patient | None, generated_resources: list[Resource],
                        group: Group | None, organization: Organization | None) -> Specimen | None:
        """Create a specimen."""
        if 'Specimen' not in self.resource_mapping:
            return None
        specimen_mapping = self.resource_mapping['Specimen']
        assert 'identifier' in specimen_mapping, f"Specimen must have an identifier {self}"
        if not specimen_mapping['identifier'].value:
            return None

        specimen_identifier = []
        identifier = None
        if isinstance(specimen_mapping['identifier'].value, list):
            # case where there are multiple specimens associated with a record
            # if len(specimen_mapping['identifier'].value) > 1:
            # print(specimen_mapping['identifier'].value)s
            identifier = [_i for _i in specimen_mapping['identifier'].value if _i.system == self._helper.system][0]
            specimen_identifier = specimen_mapping['identifier'].value
        else:
            identifier = self.populate_identifier(value=specimen_mapping['identifier'].value)
            specimen_identifier.append(identifier)

        assert identifier, f"Identifier must be created before Specimen {self}"
        assert patient, f"Patient must be created before Specimen {self}"

        specimen = self.template_specimen(subject=self.to_reference(patient))
        specimen.identifier = specimen_identifier
        specimen.id = self.mint_id(identifier=identifier, resource_type='Specimen')

        practitioner = next(iter([_ for _ in generated_resources if _.get_resource_type() == 'Practitioner']), None)

        if not organization:
            organization = next(iter([_ for _ in generated_resources if _.get_resource_type() == 'Organization']), None)

        if practitioner:
            practitioner_reference = self.to_reference(practitioner)
            if practitioner_reference.reference:
                if not specimen.collection:
                    specimen.collection = SpecimenCollection()
                specimen.collection.collector = practitioner_reference
        elif organization:
            organization_reference = self.to_reference(organization)
            if organization_reference.reference:
                if not specimen.collection:
                    specimen.collection = SpecimenCollection()
                specimen.collection.collector = organization_reference

        for field, info in specimen_mapping.items():
            if field == 'identifier':
                # already processed this
                continue
            if field == 'subject':
                # already processed this
                continue
            field_root = field.split('.')[0].split('[')[0]
            if not hasattr(specimen, field_root):
                logger.warning(f"Specimen has no field {field} {info['value']}")
                continue
            try:
                if 'parent' == field:
                    if isinstance(info, list) and len(info) > 0:
                        specimen.parent = info
                        # [setattr(specimen, field, item) for item in info] generates error: AttributeError: 'list' object has no attribute 'value'
                    else:
                        continue
                else:
                    value = info.value

                    # TODO - there should be a more elegant way to do this
                    # TODO for now, let's maintain these nested fields manually :-(  - need to use templates
                    # if 'collection.bodySite' == field:
                    #     specimen.collection.bodySite = self.to_codeable_reference(concept=self.populate_codeable_concept(code=value, display=value))
                    #     continue
                    # if 'processing[0].method' == field:
                    #     specimen.processing[0].method = self.populate_codeable_concept(code=value, display=value)
                    #     continue
                    # if 'parent' == field:
                    #     parent_identifier = self.populate_identifier(value=value)
                    #     parent_id = self.mint_id(identifier=parent_identifier, resource_type='Specimen')
                    #     specimen.parent = [Reference(reference=f"Specimen/{parent_id}")]
                    #     continue

                    if field not in specimen.__fields__:
                        if f'not_found_{field}' not in self.logged_already:
                            logger.debug(f"{field} not found in Specimen, handle in transformer")
                            self.logged_already.append(f'not_found_{field}')
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

        if 'code' in condition_mapping:
            condition.code = condition_mapping['code'].value

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
            identifier = self.populate_identifier(
                value=patient.identifier[0].value + '/Procedure/' + procedure_mapping['code'].value)
        else:
            identifier = self.populate_identifier(value=procedure_mapping['identifier'].value)

        procedure = self.template_procedure(subject=self.to_reference(patient))
        procedure.code = procedure_mapping['code'].value
        procedure.identifier = [identifier]
        procedure.id = self.mint_id(identifier=identifier, resource_type='Procedure')
        procedure.subject = self.to_reference(patient)

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

    @staticmethod
    def fetch_chembl_data(compounds: list, limit: int) -> list:
        def get_chembl_compound_info(db_file_path: str, drug_names: list, _limit=limit) -> list:
            """Query Chembl COMPOUND_RECORDS by COMPOUND_NAME for FHIR Substance"""
            if len(drug_names) == 1:
                _drug_names = tuple([x.upper() for x in [drug_names[0], drug_names[0]]])
            else:
                _drug_names = tuple([x.upper() for x in drug_names])

            query = f"""
            SELECT DISTINCT 
                a.CHEMBL_ID,
                c.STANDARD_INCHI,
                c.CANONICAL_SMILES,
                cr.COMPOUND_NAME
            FROM 
                MOLECULE_DICTIONARY as a
            LEFT JOIN 
                COMPOUND_STRUCTURES as c ON a.MOLREGNO = c.MOLREGNO
            LEFT JOIN 
                ACTIVITIES as p ON a.MOLREGNO = p.MOLREGNO
            LEFT JOIN 
                compound_records as cr ON a.MOLREGNO = cr.MOLREGNO
            LEFT JOIN
                source as sr ON cr.SRC_ID = sr.SRC_ID
            WHERE cr.COMPOUND_NAME IN {_drug_names}
            LIMIT {str(_limit)};
            """
            conn = sqlite3.connect(db_file_path)
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            conn.close()

            return rows

        def tuple_to_dict(keys, values):
            return dict(zip(keys, values))

        drug_compound_data = get_chembl_compound_info(db_file_path=CHEMBL_DB_PATH, drug_names=compounds)

        key_info = ["CHEMBL_ID", "STANDARD_INCHI", "CANONICAL_SMILES", "COMPOUND_NAME"]
        _dict_list = []
        for item in drug_compound_data:
            _dict_list.append(tuple_to_dict(key_info, item))
        return _dict_list

    @staticmethod
    def create_substance_definition_representations(drug_data: list) -> list:
        representations = []
        for row in drug_data:
            if 'STANDARD_INCHI' in row and row['STANDARD_INCHI'] is not None:
                representations.append(SubstanceDefinitionStructureRepresentation(
                    **{"representation": row['STANDARD_INCHI'],
                       "format": CodeableConcept(**{"coding": [{"code": "InChI",
                                                                "system": 'http://hl7.org/fhir/substance-representation-format',
                                                                "display": "InChI"}]})}))

            if 'CANONICAL_SMILES' in row and row['CANONICAL_SMILES'] is not None:
                representations.append(SubstanceDefinitionStructureRepresentation(
                    **{"representation": row['CANONICAL_SMILES'],
                       "format": CodeableConcept(**{"coding": [{"code": "SMILES",
                                                                "system": 'http://hl7.org/fhir/substance-representation-format',
                                                                "display": "SMILES"}]})}))
        return representations

    def create_substance_definition(self, compound_name: str, representations: list) -> SubstanceDefinition:
        sub_def_identifier = Identifier(**{"system": self.SYSTEM_chEMBL, "value": compound_name, "use": "official"})
        sub_def_id = self.mint_id(identifier=sub_def_identifier, resource_type="SubstanceDefinition")

        return SubstanceDefinition(**{"id": sub_def_id,
                                      "identifier": [sub_def_identifier],
                                      "structure": SubstanceDefinitionStructure(**{"representation": representations}),
                                      "name": [SubstanceDefinitionName(**{"name": compound_name})]
                                      })

    def create_substance(self, compound_name: str, substance_definition: SubstanceDefinition) -> Substance:
        code = None
        if substance_definition:
            code = CodeableReference(
                **{"concept": CodeableConcept(**{"coding": [
                    {"code": compound_name, "system": "/".join([self.SYSTEM_chEMBL, "compound_name"]),
                     "display": compound_name}]}),
                   "reference": Reference(**{"reference": f"SubstanceDefinition/{substance_definition.id}"})})

        sub_identifier = Identifier(
            **{"system": self.SYSTEM_chEMBL, "value": compound_name, "use": "official"})
        sub_id = self.mint_id(identifier=sub_identifier, resource_type="Substance")

        return Substance(**{"id": sub_id,
                            "identifier": [sub_identifier],
                            "instance": True,  # place-holder
                            "category": [CodeableConcept(**{"coding": [{"code": "drug",
                                                                        "system": "http://terminology.hl7.org/CodeSystem/substance-category",
                                                                        "display": "Drug or Medicament"}]})],
                            "code": code})

    def create_medication(self, compound_name: Optional[str], treatment_type: Optional[str],
                          _substance: Optional[Substance], generated_resources: list[Resource]) -> Medication:

        if compound_name:
            if ":" in compound_name:
                compound_name.replace(":", "_")
            code = CodeableConcept(**{"coding": [
                {"code": compound_name, "system": "/".join([self.SYSTEM_chEMBL, "compound_name"]),
                 "display": compound_name}]})

            med_identifier = Identifier(
                **{"system": self.SYSTEM_chEMBL, "value": compound_name, "use": "official"})
        else:
            if ":" in treatment_type:
                treatment_type.replace(":", "_")

            code = CodeableConcept(**{
                "coding": [{"code": treatment_type,
                            "system": "/".join([self._helper.system, "treatment_type"]),  # TODO: change
                            "display": treatment_type}]})

            med_identifier = Identifier(
                **{"system": self._helper.system, "value": treatment_type, "use": "official"})

        med_id = self.mint_id(identifier=med_identifier, resource_type="Medication")

        ingredients = []
        if _substance:
            ingredients.append(MedicationIngredient(**{
                "item": CodeableReference(
                    **{"reference": Reference(**{"reference": f"Substance/{_substance.id}"})})}))

        return Medication(**{"id": med_id,
                             "identifier": [med_identifier],
                             "code": code,
                             "ingredient": ingredients})

    def chembl2medication(self, generate_resources: list[Resource]):
        # duplicate attempt to pull out query logic
        medications = []

        for field, field_info in self.model_fields.items():
            if not field_info.json_schema_extra:
                continue

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.medication" or \
                    field_info.json_schema_extra['fhir_resource_type'] == "Medication.ingredient":
                medication_name = getattr(self, field)
                if medication_name:
                    medications.append(medication_name)

        chembl_information = self.fetch_chembl_data(medications, limit=1000)

        if chembl_information:
            drug_name = []
            for row in chembl_information:
                if 'COMPOUND_NAME' in row and row['COMPOUND_NAME'] is not None:
                    drug_name.append(row['COMPOUND_NAME'])
            study_drugs = list(set(drug_name))

            for medication_name in study_drugs:
                drug_chembl_data = []
                for row in chembl_information:
                    if ('COMPOUND_NAME' in row and row['COMPOUND_NAME']
                            is not None and row['COMPOUND_NAME'] == medication_name):
                        drug_chembl_data.append(row)

                if drug_chembl_data:
                    sdr = self.create_substance_definition_representations(drug_chembl_data)
                    if sdr:
                        sd = self.create_substance_definition(compound_name=medication_name, representations=sdr)
                        if sd:
                            generate_resources.append(sd)
                            substance = self.create_substance(compound_name=medication_name, substance_definition=sd)
                            if substance:
                                generate_resources.append(substance)
                                medication = self.create_medication(compound_name=medication_name, treatment_type=None,
                                                                    _substance=substance,
                                                                    generated_resources=generate_resources)
                                if medication:
                                    generate_resources.append(medication)

            return generate_resources

    def create_medication_administration(self, patient: Patient,
                                         generated_resources: list[Resource]) -> list[Resource] | None:
        """
        creates MedicationAdministration
            - if treatment type or drug name exists - make MedicationAdministration
            - if treatment end index days exists, then status -> completed, else status is defined by user
                (matching fhir requirnments) or unknown
            - if drug name is null, then Medication.code -> snomed_code: Unknown 261665006
            - Medication.ingredient.item -> Substance.code -> SubstanceDefinition
            - status, medication, subject are required by FHIR
        """
        # TODO: this function runs 5s per record which can add up on 1000+ records will have to create all Medications prior to this call
        assert patient, f"Medication Administration requires the patient information"

        status = None
        medication = None
        medication_name = None
        index_end = None
        index_start = None
        admin_reason = []
        status_reason = []
        status_reason_value = None
        total_dose_quantity = None
        dose_route_code = None
        dose_rate_quantity = None
        med_admin_dosage = None
        substance = None
        secondary_identifier = None

        note = []

        for field, field_info in self.model_fields.items():
            if not field_info.json_schema_extra:
                continue

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.medication" or \
                    field_info.json_schema_extra['fhir_resource_type'] == "Medication.ingredient":
                medication_name = getattr(self, field)

                drug_chembl_data = self.fetch_chembl_data([medication_name], limit=50)

                if drug_chembl_data:
                    sdr = self.create_substance_definition_representations(drug_chembl_data)
                    if sdr:
                        sd = self.create_substance_definition(compound_name=medication_name, representations=sdr)
                        if sd:
                            generated_resources.append(sd)
                            substance = self.create_substance(compound_name=medication_name, substance_definition=sd)
                            if substance:
                                generated_resources.append(substance)

                # not all med have chembl information
                medication = self.create_medication(compound_name=medication_name, treatment_type=None,
                                                    _substance=substance,
                                                    generated_resources=generated_resources)
                if medication:
                    generated_resources.append(medication)

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.reason.concept":
                admin_reason_value = getattr(self, field)
                if admin_reason_value:
                    admin_reason = [CodeableReference(
                        **{"concept": CodeableConcept(**{
                            "coding": [{"code": admin_reason_value,
                                        "system": self._helper.system,
                                        "display": admin_reason_value}]})})]

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.statusReason":
                status_reason_value = getattr(self, field)

                if status_reason_value:
                    status_reason = [CodeableConcept(**{"coding": [{
                        "code": status_reason_value,
                        "system": self._helper.system,
                        "display": status_reason_value}]})]

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.dosage.dose":
                total_dose = getattr(self, field)
                if total_dose:
                    total_dose_quantity = Quantity(**{"value": round(total_dose, 2)})

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.dosage.rateQuantity":
                dose_rate = getattr(self, field)
                if dose_rate:
                    dose_rate_quantity = Quantity(**{"value": round(dose_rate, 2)})

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.dosage.route":
                dose_route = getattr(self, field)
                if not dose_route:
                    dose_route = "Unknown"
                dose_route_code = CodeableConcept(**{
                    "coding": [{"code": dose_route,
                                "system": self._helper.system,
                                "display": dose_route}]})

            if total_dose_quantity:
                med_admin_dosage = MedicationAdministrationDosage(**{"dose": total_dose_quantity,
                                                                     "route": dose_route_code,
                                                                     "rateQuantity": dose_rate_quantity})
                # print(f"MedicationAdministration dosage: {med_admin_dosage.json()}")

            if field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.note":
                note_content = getattr(self, field)
                if note_content:
                    note.append(Annotation(**{"text": note_content}))

            # TODO: move this out - STUDY SPECIFIC
            if field_info.json_schema_extra['fhir_resource_type'] == "Identifier.secondary":
                ident_value = getattr(self, field)
                if ident_value:
                    secondary_identifier = Identifier(**{"system": "/".join([self._helper.system, "regimen"]), "use": "secondary", "value": ident_value})
                    print(f"IDENTIFIER REGIM: {ident_value}, {secondary_identifier}")

            if field_info.json_schema_extra[
                'fhir_resource_type'] == "MedicationAdministration.occurrenceTiming.boundsRange.high":
                index_end = getattr(self, field)  # TODO: do we need a more general way to define treatment was completed/stopped?
                status = "completed"
            elif field_info.json_schema_extra['fhir_resource_type'] == "MedicationAdministration.status":
                status_value = getattr(self, field)
                if status_reason_value:
                    status = 'stopped'
                elif status_value in ['in-progress', 'not-done', 'on-hold', 'completed', 'entered-in-error', 'stopped',
                                      'unknown']:
                    status = status_value
                else:
                    status = "unknown"

            if field_info.json_schema_extra[
                'fhir_resource_type'] == "MedicationAdministration.occurrenceTiming.boundsRange.low":
                index_start = getattr(self, field)

        timing = Timing(**{"repeat": TimingRepeat(**{"boundsRange": Range(**{"low": Quantity(**{"value": 0}),
                                                                             "high": Quantity(**{
                                                                                 "value": 1})})})})  # place holder - required by FHIR
        if index_start and index_end:
            timing = Timing(**{"repeat": TimingRepeat(**{"boundsRange": Range(
                **{"low": Quantity(**{"value": int(index_start)}), "high": Quantity(**{"value": int(index_end)})})})})


        # add in date notion to identifier
        medication_admin_identifier = Identifier(
            **{"system": self._helper.system, "use": "official", "value": "-".join([patient.id, medication_name])})
        medication_admin_id = self.mint_id(identifier=medication_admin_identifier,
                                           resource_type="MedicationAdministration")

        medication_code = CodeableConcept(**{"coding": [{"code": medication_name,
                                                         "system": self._helper.system,
                                                         "display": medication_name}]})

        if not medication:
            # information not in chembl
            med_identifier = Identifier(
                **{"system": self._helper.system, "value": medication_name, "use": "official"})

            med_id = self.mint_id(identifier=med_identifier, resource_type="Medication")

            code = CodeableConcept(**{
                "coding": [{"code": medication_name,
                            "system": "/".join([self._helper.system, "medication"]),
                            "display": medication_name}]})

            medication = Medication(**{"id": med_id,
                                       "identifier": [med_identifier],
                                       "code": code})

        medication_codeable_reference = CodeableReference(**{"concept": medication_code, "reference": Reference(
            **{"reference": f"Medication/{medication.id}"})})

        # ingredient.strengthQuantity.unit
        # ingredient.strengthQuantity.value
        # Identifier.secondary
        _identifiers = []
        if secondary_identifier:
            _identifiers.append(secondary_identifier)
        if medication_admin_identifier:
            _identifiers.append(medication_admin_identifier)

        # TODO: move this out - STUDY SPECIFIC
        if index_start:
            time_identifier = Identifier(
                **{"system": "/".join([self._helper.system, "index_date_start_days"]), "use": "secondary", "value": index_start})
            if time_identifier:
                _identifiers.append(time_identifier)

        data = {"id": medication_admin_id,
                "identifier": _identifiers,
                "status": status,
                "statusReason": status_reason,
                "reason": admin_reason,
                "medication": medication_codeable_reference,
                "subject": {
                    "reference": f"Patient/{patient.id}"
                },
                "occurenceTiming": timing,
                "dosage": med_admin_dosage,
                "note": note}

        med_admin = MedicationAdministration(**data)

        if med_admin:
            generated_resources.append(med_admin)
            # print(med_admin.json(), "\n")
        return generated_resources

    def default_transform(self, research_study: ResearchStudy) -> list[Resource]:
        """Default transformation, call this method if you don't want to implement your own transform."""

        # "process" mappings

        generated_resources: list[Resource] = [research_study]

        practioner = self.create_practioner(generated_resources)
        if practioner:
            generated_resources.extend([practioner])

        organization = self.create_organization(generated_resources)
        if organization:
            generated_resources.extend([organization])

        patient = self.create_patient(generated_resources)
        if patient:
            research_subject = self.create_research_subject(patient, research_study)
            generated_resources.extend([patient, research_subject])

        specimen = self.create_specimen(patient, generated_resources, group=None, organization=organization)
        if specimen:
            generated_resources.append(specimen)

        condition = self.create_condition(patient, generated_resources)
        if condition:
            generated_resources.append(condition)

        procedure = self.create_procedure(patient, generated_resources)
        if procedure:
            generated_resources.append(procedure)

        # self.chembl2medication(generated_resources)
        has_medication_mapping = any(
            "Medication" in field_info.json_schema_extra.get('fhir_resource_type', '') or
            "MedicationAdministration.medication" in field_info.json_schema_extra.get('fhir_resource_type', '')
            for field, field_info in self.model_fields.items()
        )

        if has_medication_mapping:
            print("Creating MedicationAdministration----")
            self.create_medication_administration(patient, generated_resources)

        generated_observations = []
        for _ in generated_resources:
            observations = self.create_observations(subject=patient, focus=_)
            if observations:
                generated_observations.extend(observations)
        generated_resources.extend(generated_observations)

        assert all([_ for _ in generated_resources]), "Should not have a None"
        return generated_resources

    def create_observations(self, subject, focus, jinja_observation_code=None) -> list[Observation]:
        """Create observations."""
        observations = []

        # TODO - we already have self.observation_mapping, so we can use that?
        observation_fields = {}
        observation_components = {}
        observation_identifier = None
        observation_code = None
        observation = None
        components = []
        observation_focus = None
        focus_resource_type = None
        resource_type = None

        for field, field_info in self.model_fields.items():  # noqa - implementers must implement this method ie inherit from BaseModel
            if not field_info.json_schema_extra:
                continue
            if 'observation_subject' in field_info.json_schema_extra:
                if isinstance(focus, list):
                    resource_type = []
                    for focus_item in focus:
                        resource_type.append(focus_item.get_resource_type())
                    if len(list(set(resource_type))) == 1 and resource_type[0] == field_info.json_schema_extra[
                        'observation_subject']:
                        focus_resource_type = field_info.json_schema_extra['observation_subject']
                else:
                    focus_resource_type = focus.get_resource_type()
                if focus_resource_type == None and isinstance(focus, list):
                    for focus_item in focus:
                        resource_type.append(focus_item.get_resource_type())
                    if len(list(set(resource_type))) == 1:
                        focus_resource_type = resource_type[0]
                    elif focus:
                        focus_resource_type = focus[0].resource_type  # temp solution
                if field_info.json_schema_extra['observation_subject'] == focus_resource_type:
                    observation_fields[field] = field_info
            if 'fhir_resource_type' in field_info.json_schema_extra and field_info.json_schema_extra[
                'fhir_resource_type'] == 'Observation.component':
                observation_components[field] = field_info

            # if 'fhir_resource_type' in field_info.json_schema_extra and field_info.json_schema_extra['fhir_resource_type'] == 'Observation.identifier':
            #     value = getattr(self, field)
            #     # this is when we want to create an observation all attributes in the row
            #     identifier = self.observation_identifier(value, focus, subject)

            if 'fhir_resource_type' in field_info.json_schema_extra and field_info.json_schema_extra[
                'fhir_resource_type'] == 'Observation.code':
                value = getattr(self, field)
                underscored_code = inflection.underscore(field)
                display = field_info.description
                if not display:
                    display = value
                if not display:
                    display = 'Unknown'
                observation_code = self.populate_codeable_concept(code=underscored_code, display=display)

        for component_field, component_field_info in observation_components.items():
            component_value = getattr(self, component_field)
            underscored_component_field = inflection.underscore(component_field)
            component = ObservationComponent(
                code={
                    'coding': [
                        {
                            'system': self._helper.system,
                            'code': underscored_component_field,
                            'display': component_field,
                        }
                    ],
                    'text': component_field
                }
            )

            # TODO value[x]
            field_type = str(component_field_info.annotation)
            if 'int' in field_type:
                component.valueInteger = getattr(self, component_field)
            elif 'float' in field_type or 'decimal' in field_type or 'number' in field_type:
                component.valueQuantity = self.to_quantity(field=component_field, field_info=component_field_info,
                                                           value=component_value)
            elif 'bool' in field_type:
                component_value = getattr(self, component_field)
                if isinstance(component_value, bool):
                    component.valueBoolean = component_value

            elif component_value and isinstance(getattr(self, component_field), str):
                component_value = getattr(self, component_field)
                component.valueString = str(component_value)

            if component:
                components.append(component)
                if isinstance(focus, list):
                    observation_focus = [self.to_reference(_f) for _f in focus]
                else:
                    if component_field_info.json_schema_extra['observation_subject'] == focus.get_resource_type():
                        observation_focus = [
                            self.to_reference(focus)]  # should be the same focus reference for the component use-case
        if isinstance(focus, list):
            focus_reference = [self.to_reference(_f) for _f in focus]
        else:
            focus_reference = self.to_reference(focus)

        if components and observation_focus:
            code = None
            observation_dict = self.render_template(f"Observation.yaml.jinja")

            if 'code' in observation_dict and not observation_code:
                coding_list = observation_dict['code'].get('coding', [])
                if coding_list or observation_dict['code'].get('text'):
                    code = observation_dict['code']
                    del observation_dict['code']
                else:
                    # print("empty or invalid 'code' field detected, assigning default:", observation_dict['code'])
                    if "Specimen" in focus_reference.reference:
                        code = self.populate_codeable_concept(system="https://loinc.org/",
                                                              code="68992-7",
                                                              display="Specimen-related information panel")
                    elif "Patient" in focus_reference.reference:
                        code = self.populate_codeable_concept(system="https://loinc.org/",
                                                              code="68992-7",
                                                              display="Specimen-related information panel")
                    del observation_dict['code']

            observation = Observation(
                **observation_dict,
                code=code
            )

            if jinja_observation_code:
                field_code = jinja_observation_code
            else:
                field_code = code
            identifier = self.observation_identifier(field=field_code, focus=focus, subject=subject)
            assert identifier, f"Can't proceed, Observation with focus: {focus} is missing Identifier."
            id_ = self.mint_id(identifier=identifier, resource_type='Observation')

            observation.id = id_
            observation.identifier = [identifier]
            observation.subject = self.to_reference(subject)
            observation.focus = observation_focus

            observation.component = components

            observations.append(observation)

        if not components:
            # for all attributes in raw record ...
            for field, field_info in observation_fields.items():

                # that are not null ...
                value = getattr(self, field)
                if not value:
                    continue

                # this is when we want to create an observation for each attribute in the row
                identifier = None
                if not observation_identifier:

                    identifier = self.observation_identifier(field, focus, subject)
                    if 'fhir_resource_type' in field_info.json_schema_extra and field_info.json_schema_extra[
                        'fhir_resource_type'] == 'Observation.identifier':
                        value = getattr(self, field)
                        # this is when we want to create an observation all attributes in the row
                        identifier = self.observation_identifier(value, focus, subject)
                else:
                    identifier = observation_identifier

                id_ = self.mint_id(identifier=identifier, resource_type='Observation')
                more_codings = additional_observation_codings(field_info)

                try:
                    observation_dict = self.render_template(f"Observation-{field}.yaml.jinja")
                except Exception as e:
                    observation_dict = self.render_template(f"Observation.yaml.jinja")

                code = None
                focus_reference = self.to_reference(focus)

                if 'code' in observation_dict and not observation_code:
                    coding_list = observation_dict['code'].get('coding', [])
                    if coding_list or observation_dict['code'].get('text'):
                        code = observation_dict['code']
                        del observation_dict['code']
                    else:
                        # print("empty or invalid 'code' field detected, assigning default:", observation_dict['code'])
                        if "Specimen" in focus_reference.reference:
                            code = self.populate_codeable_concept(system="https://loinc.org/",
                                                                  code="68992-7",
                                                                  display="Specimen-related information panel")
                        elif "Patient" in focus_reference.reference:
                            code = self.populate_codeable_concept(system="https://loinc.org/",
                                                                  code="68992-7",
                                                                  display="Specimen-related information panel")
                        del observation_dict['code']

                if not code:
                    if not observation_code and focus:
                        # Default code: adding general required Observation code based on the focus of Observation
                        if "Specimen" in focus_reference.reference:
                            code = self.populate_codeable_concept(system="https://loinc.org/",
                                                                  code="68992-7",
                                                                  display="Specimen-related information panel")
                        elif "Patient" in focus_reference.reference:
                            code = self.populate_codeable_concept(system="https://loinc.org/",
                                                                  code="68992-7",
                                                                  display="Specimen-related information panel")
                    elif not observation_code and not focus:
                        underscored_code = inflection.underscore(field)
                        display = field_info.description
                        if not display:
                            display = value
                        code = self.populate_codeable_concept(code=underscored_code, display=display)
                    else:
                        code = observation_code

                observation = Observation(
                    **observation_dict,
                    code=code
                )

                observation.id = id_
                observation.identifier = [identifier]
                observation.subject = self.to_reference(subject)
                observation.focus = [focus_reference]

                # if there are components, then the value[x] is not set
                if not observation.component:
                    # value[x] the annotations are often decorated with Optional, so cast to string and check for the type
                    field_type = str(field_info.annotation)
                    if 'int' in field_type:
                        observation.valueInteger = getattr(self, field)
                    elif 'float' in field_type or 'decimal' in field_type or 'number' in field_type:
                        observation.valueQuantity = self.to_quantity(field=field, field_info=field_info)
                    else:
                        observation.valueString = getattr(self, field)

                # if we have component - remove value[x]
                if observation.component:
                    if hasattr(observation, 'valueInteger'):
                        del observation.valueInteger
                    if hasattr(observation, 'valueQuantity'):
                        del observation.valueQuantity
                    if hasattr(observation, 'valueString'):
                        del observation.valueString

                if more_codings:
                    observation.code.coding.extend(
                        more_codings)  # noqa - unclear? Unresolved attribute reference 'coding' for class 'CodeableConceptType'

            if observation:
                observations.append(observation)

        return observations

    def observation_identifier(self, field, focus, subject):
        subject_identifier = self._helper.get_official_identifier(subject).value
        if isinstance(focus, list):
            focus_identifiers = [self._helper.get_official_identifier(_f).value for _f in focus]
            focus_identifier = "-".join(focus_identifiers)
        else:
            focus_identifier = self._helper.get_official_identifier(focus).value
        if field:
            identifier = self.populate_identifier(value=f"{subject_identifier}-{focus_identifier}-{field}")
        else:
            # component dependent
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

    def to_reference(self, resource: Resource) -> Reference:
        """Create a reference from a resource of the form RESOURCE/id."""
        return Reference(reference=f"{resource.get_resource_type()}/{resource.id}")

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
        condition_dict = self.render_template("Condition.yaml.jinja")
        return Condition(**condition_dict, subject=self.to_reference(subject))

    def template_procedure(self, subject: Patient) -> Procedure:
        """Create a generic procedure."""
        # dispatch to jinja
        procedure_dict = self.render_template("Procedure.yaml.jinja")
        assert subject, f"Subject must be created before Procedure {self}"
        assert subject.id, f"Subject must have an id before Procedure"
        return Procedure(**procedure_dict, subject=self.to_reference(subject))

    def template_specimen(self, *args: Any, **kwargs: Any) -> Specimen:
        """Create a generic specimen."""
        # dispatch to jinja
        # _ = self.render_template("Specimen.yaml.jinja")
        # # print('>', _, '<')
        # print(_['collection']['bodySite'])
        _ = Specimen(**self.render_template("Specimen.yaml.jinja"))
        if 'subject' in kwargs:
            _.subject = kwargs['subject']
        return _

    def template_patient(self, *args: Any, **kwargs: Any) -> Patient:
        """Create a generic patient."""
        # dispatch to jinja
        return Patient(**self.render_template("Patient.yaml.jinja"))

    def template_practitioner(self, *args: Any, **kwargs: Any) -> Practitioner:
        """Create a generic practitioner."""
        # dispatch to jinja
        return Practitioner(**self.render_template("Practitioner.yaml.jinja"))

    def template_organization(self, *args: Any, **kwargs: Any) -> Organization:
        """Create a generic organization."""
        # dispatch to jinja
        return Organization(**self.render_template("Organization.yaml.jinja"))

    @classmethod
    def template_dir(cls) -> pathlib.Path:
        """Return the template dir."""
        _ = pathlib.Path(os.path.dirname(inspect.getfile(cls)))
        _ = _ / 'templates'
        _.parent.mkdir(parents=True, exist_ok=True)
        return _


def generate_templates(target_template_dir: pathlib.Path, overwrite: bool = False) -> None:
    """Generate templates."""

    reference_templates = Environment(loader=PackageLoader('g3t_etl'), autoescape=select_autoescape())
    reference_observation_template = None
    for _ in reference_templates.list_templates():
        src_template_path = pathlib.Path(reference_templates.get_template(_).filename)
        assert src_template_path.exists(), f"Template {src_template_path} not found"
        target_template_path = target_template_dir / src_template_path.name
        if src_template_path.name == 'Observation.yaml.jinja':
            reference_observation_template = src_template_path
        if not overwrite and target_template_path.exists():
            click.secho(f"Skipping existing {target_template_path} (see --overwrite).", fg='yellow', file=sys.stderr)
        else:
            shutil.copy(src_template_path, target_template_path)
            click.secho(f"Created {target_template_path}", fg='green', file=sys.stderr)

    #  TODO - dynamically generate observation templates by loading the pydantic models


#     transformer = cls()
#     for _ in transformer.observation_mapping:
#         target_template_path = target_template_dir / f"Observation-{_.field}.yaml.jinja"
#         if not overwrite and target_template_path.exists():
#             click.secho(f"Skipping existing {target_template_path} (see --overwrite).", fg='yellow', file=sys.stderr)
#         else:
#             # the annotations are often decorated with Optional, so cast to string and check for the type
#             field_type = str(_.field_info.annotation)
#             value_x = None
#             if 'int' in field_type:
#                 value_x = "valueInteger: {{ " + f"transformer.{_.field}" + " }}"
#             elif 'float' in field_type or 'decimal' in field_type or 'number' in field_type:
#                 vq = transformer.to_quantity(field=_.field, field_info=_.field_info)
#                 vq['value'] = "{{ " + f"transformer.{_.field}" + " }}"
#                 if 'system' in vq:
#                     value_x = """
# valueQuantity:
# value: VALUE
# system: SYSTEM
# code: CODE
# unit: UNIT
#                     """.replace('SYSTEM', vq['system']) \
#                         .replace('CODE', vq['code']) \
#                         .replace('UNIT', vq['unit']) \
#                         .replace('VALUE', vq['value']) \
#                         .replace('\n', '', 1)
#
#                 else:
#                     value_x = """
# valueQuantity:
# value: VALUE
#                       """.replace('VALUE', vq['value']) \
#                         .replace('\n', '', 1)
#             else:
#                 value_x = "valueString: {{ " + f"transformer.{_.field}" + " }}"
#
#             observation_template = reference_templates.get_template('Observation.yaml.jinja').render(value_x=value_x)
#             with open(target_template_path, 'w') as fp:
#                 fp.write(observation_template)
#             click.secho(f"Created {target_template_path}", fg='green', file=sys.stderr)


TRANSFORMER_TEMPLATE = '''
import logging
from typing import Any

from fhir.resources.researchstudy import ResearchStudy
from fhir.resources.resource import Resource
from g3t_etl import factory
from g3t_etl.transformer import FHIRTransformer
from .SUBMISSION_PATH import SUBMISSION_CLASS


logger = logging.getLogger(__name__)


class TRANSFORMER_CLASS(SUBMISSION_CLASS, FHIRTransformer):
    """Generated Transformer class. Generated NOW"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa
        """Initialize the transformer, initialize the dictionary and the helper class."""
        SUBMISSION_CLASS.__init__(self, **kwargs, )
        FHIRTransformer.__init__(self, **kwargs, )

    def transform(self, research_study: ResearchStudy = None) -> list[Resource]:
        """Plugin manager will call this function to transform the data to FHIR."""
        # we can do whatever we want here, but for now we'll just return the default transform
        return self.default_transform(research_study=research_study)


def register() -> None:
    factory.register(
        transformer=TRANSFORMER_CLASS
    )
'''


def is_valid_fhir_resource_type(resource_type):
    """gets FHIR resource type string name"""
    try:
        model_class = get_fhir_model_class(resource_type)
        return model_class is not None
    except KeyError:
        return False


def create_or_extend(new_items, folder_path='META', resource_type='Observation', update_existing=False):
    """create or extend onto an existing FHIR resource ndjson file """
    assert is_valid_fhir_resource_type(resource_type), f"Invalid resource type: {resource_type}"

    file_name = "".join([resource_type, ".ndjson"])
    file_path = os.path.join(folder_path, file_name)

    file_existed = os.path.exists(file_path)

    existing_data = {}

    if file_existed:
        with open(file_path, 'r') as file:
            for line in file:
                try:
                    item = orjson.loads(line)
                    existing_data[item.get("id")] = item
                except orjson.JSONDecodeError:
                    continue

    for new_item in new_items:
        new_item_id = new_item["id"]
        if new_item_id not in existing_data or update_existing:
            existing_data[new_item_id] = new_item

    with open(file_path, 'w') as file:
        for item in existing_data.values():
            file.write(orjson.dumps(item).decode('utf-8') + '\n')

    if file_existed:
        if update_existing:
            print(f"{file_name} has new updates to existing data.")
        else:
            print(f"{file_name} has been extended, without updating existing data.")
    else:
        print(f"{file_name} has been created.")


def generate_transformer(submission_source_path: pathlib.Path, overwrite: bool = False) -> None:
    """Generate a transformer."""
    target_path = submission_source_path.parent / (submission_source_path.stem + '_transformer.py')
    if not overwrite and target_path.exists():
        click.secho(f"Skipping existing {target_path} (see --overwrite).", fg='yellow', file=sys.stderr)
        return

    clazz = TRANSFORMER_TEMPLATE.replace('SUBMISSION_PATH', submission_source_path.stem)
    clazz = clazz.replace('SUBMISSION_CLASS', inflection.camelize(submission_source_path.stem))
    clazz = clazz.replace('TRANSFORMER_CLASS', inflection.camelize(target_path.stem))
    clazz = clazz.replace('NOW', str(datetime.now().isoformat()))
    with open(target_path, 'w') as fp:
        fp.write(clazz)
    click.secho(f"Created: {target_path}", fg='green', file=sys.stderr)
