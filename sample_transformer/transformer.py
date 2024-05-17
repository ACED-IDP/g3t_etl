import logging
import re
from typing import Any, Optional

from fhir.resources.identifier import Identifier
from fhir.resources.researchstudy import ResearchStudy
from fhir.resources.resource import Resource
from pydantic import BaseModel, computed_field

from g3t_etl import factory
from g3t_etl.transformer import FHIRTransformer
from sample_transformer.submission import Submission

logger = logging.getLogger(__name__)


class DeconstructedID(BaseModel):
    """Split the id into component parts."""
    patient_id: str
    mri_area: Optional[int] = None
    time_points: Optional[list[str]] = None
    tissue_block: Optional[int] = None


def split_id(id_str) -> None | DeconstructedID:
    """Format: XXX_Y_Z_H, where:
    XXX is patient ID,
    Y is the MRI area number lesion,
    Z are the time points (A or B), which may occur multiple times,
    H is the tissue block number in case of multiple biopsy blocks per area"""

    # Define a regular expression pattern to match the specified format
    pattern = r"^(?P<patient_id>[^_]+)_(?P<mri_area>[^_]+)_(?P<time_points>[AB_]+)(?:_(?P<tissue_block>[^_]+))?$"

    # Try to match the pattern with the provided ID
    match = re.match(pattern, id_str)

    # If there is a match, create a PatientInfo Pydantic model
    if match:
        deconstructed_id = DeconstructedID(
            patient_id=match.group("patient_id"),
            mri_area=match.group("mri_area"),
            time_points=match.group("time_points").split("_"),
            tissue_block=match.group("tissue_block") if match.group("tissue_block") else None
        )
        return deconstructed_id
    else:
        # otherwise None
        return None


class SimpleTransformer(Submission, FHIRTransformer):
    """Performs the most simple transformation possible."""


    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa
        """Initialize the transformer, initialize the dictionary and the helper class."""
        Submission.__init__(self, **kwargs, )
        FHIRTransformer.__init__(self, **kwargs, )

        # uncomment if you want to see the mappings and values
        if 'debug_resource_mapping' not in self.logged_already:
            assert 'patient_identifier' in self.mapped_fields, f'patient_id not in mapped_fields {self.mapped_fields.keys()}'
            assert 'procedure_identifier' in self.mapped_fields, f'patient_id not in mapped_fields {self.mapped_fields.keys()}'
            self.logged_already.append('debug_resource_mapping')

    @computed_field
    @property
    def deconstructed_id(self) -> DeconstructedID:
        """Deconstruct the ID."""
        if not self.id:
            return None
        return split_id(self.id)

    @computed_field(json_schema_extra={'fhir_resource_type': 'Patient.identifier'})
    @property
    def patient_identifier(self) -> str:
        """Return the patient ID."""
        return self.deconstructed_id.patient_id

    @computed_field(json_schema_extra={'fhir_resource_type': 'Procedure.identifier'})
    @property
    def procedure_identifier(self) -> str:
        """Return the mri_area ID."""
        deconstructed_id = self.deconstructed_id
        time_points = '_'.join(deconstructed_id.time_points)
        lesion_identifier = f"{deconstructed_id.mri_area}_{time_points}"
        if deconstructed_id.tissue_block:
            lesion_identifier += f"_{deconstructed_id.tissue_block}"
        return f"{deconstructed_id.patient_id}/{lesion_identifier}/{self.procedure_occurrence_age['value']}"

    @computed_field(json_schema_extra={'fhir_resource_type': 'Condition.identifier'})
    @property
    def condition_identifier(self) -> Identifier:
        """Return the mri_area ID."""
        # loaded from spreadsheet
        # TODO code = condition_mapping['code'].value
        # assert 'code' in self.mapped_fields['Condition'], f'condition_code not in mapped_fields {self.mapped_fields.keys()}'
        return self.populate_identifier(value=self.deconstructed_id.patient_id + '/Condition')

    @computed_field(json_schema_extra={'fhir_resource_type': 'Procedure.code'})
    @property
    def procedure_code(self) -> str:
        """Return the snomed code."""
        return self.populate_codeable_concept(system="http://snomed.info/sct", code="81068001",
                                              display="Fine needle aspiration biopsy of prostate")

    @computed_field(
        json_schema_extra={
            'fhir_resource_type': 'Procedure.occurrenceAge',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mo',
            'uom_unit': 'month'
        }
    )
    @property
    def procedure_occurrence_age(self) -> str:
        """Calculate the occurrence age."""
        if not self.ageDiagM:
            return None
        occurrence_age = self.ageDiagM + self.months_diag
        occurrence_age = self.to_quantity(value=occurrence_age, field_info=self.model_fields['ageDiagM'])
        return occurrence_age

    def transform(self, research_study: ResearchStudy = None) -> list[Resource]:
        """Plugin manager will call this function to transform the data to FHIR."""
        return self._to_fhir(research_study=research_study)

    def _to_fhir(self, research_study: ResearchStudy) -> [Resource]:
        """Convert to FHIR, simple delegation to default_transform."""
        return self.default_transform(research_study=research_study)


def register() -> None:
    """Inform the factory of the transformer."""
    factory.register(
        transformer=SimpleTransformer,
        dictionary_path="tests/fixtures/sample_data_dictionary.xlsx",
    )
