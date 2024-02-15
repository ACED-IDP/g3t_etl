import logging
import re
import sys
from typing import Any, Optional

from fhir.resources.patient import Patient
from fhir.resources.procedure import Procedure
from fhir.resources.researchstudy import ResearchStudy
from fhir.resources.researchsubject import ResearchSubject
from fhir.resources.resource import Resource
from fhir.resources.specimen import Specimen
from pydantic import BaseModel, computed_field

from g3t_etl import factory
from g3t_etl.factory import FHIRTransformer
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
    Y is the MRI area number,
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

    @computed_field
    @property
    def deconstructed_id(self) -> DeconstructedID:
        """Deconstruct the ID."""
        return split_id(self.id)

    def transform(self, research_study: ResearchStudy = None) -> list[Resource]:
        """Plugin manager will call this function to transform the data to FHIR."""
        return self._to_fhir(self.deconstructed_id, research_study=research_study)

    def _to_fhir(self, deconstructed_id: DeconstructedID, research_study: ResearchStudy) -> [Resource]:
        """Convert to FHIR."""
        exception_msg_part = None
        research_subject = None
        try:

            exception_msg_part = 'Patient'
            identifier = self.populate_identifier(value=deconstructed_id.patient_id)
            patient = Patient(id=self.mint_id(identifier=identifier, resource_type='Patient'),
                              identifier=[identifier],
                              active=True)

            if research_study:
                exception_msg_part = 'ResearchSubject'
                identifier = self.populate_identifier(value=deconstructed_id.patient_id)
                research_subject = ResearchSubject(
                    id=self.mint_id(identifier=identifier, resource_type='ResearchSubject'),
                    identifier=[identifier],
                    status="active",
                    study={'reference': f"ResearchStudy/{research_study.id}"},
                    subject={'reference': f"Patient/{patient.id}"}
                )

            exception_msg_part = 'Procedure'

            time_points = '_'.join(deconstructed_id.time_points)
            lesion_identifier = f"{deconstructed_id.mri_area}_{time_points}"
            if deconstructed_id.tissue_block:
                lesion_identifier += f"_{deconstructed_id.tissue_block}"

            identifier = self.populate_identifier(value=f"{deconstructed_id.patient_id}/{lesion_identifier}")
            procedure = Procedure(id=self.mint_id(identifier=identifier, resource_type='Procedure'),
                                  identifier=[identifier],
                                  status="completed",
                                  subject=self.to_reference(patient))
            procedure.code = self.populate_codeable_concept(system="http://snomed.info/sct", code="312250003",
                                                            display="Magnetic resonance imaging")

            exception_msg_part = 'Specimen'
            identifier = self.populate_identifier(value=f"{self.id}")
            specimen = Specimen(id=self.mint_id(identifier=identifier, resource_type='Specimen'),
                                identifier=[identifier],
                                collection={'procedure': self.to_reference(procedure)},
                                subject=self.to_reference(patient))

            exception_msg_part = 'Condition'
            condition = self.template_condition(subject=self.to_reference(patient))
            identifier = self.populate_identifier(value=f"{deconstructed_id.patient_id}/{condition.code.text}")
            condition.id = self.mint_id(identifier=identifier, resource_type='Condition')
            condition.identifier = [identifier]
            condition.onsetAge = self.to_quantity(field="ageDiagM", field_info=self.model_fields['ageDiagM'])

            # TODO confirm these fields as Observations of the Specimen
            specimen_observations = self.create_observations(subject=patient, focus=specimen)
            condition_observations = self.create_observations(subject=patient, focus=condition)

        except Exception as e:
            print(f"Error transforming {self.id} to {exception_msg_part}: {e}", file=sys.stderr)
            raise e

        patient_graph = [patient, specimen, procedure, condition]
        if research_study and research_subject:
            patient_graph.append(research_subject)

        return patient_graph + specimen_observations + condition_observations


def register() -> None:
    factory.register(
        transformer=SimpleTransformer,
        dictionary_path="tests/fixtures/sample_data_dictionary.xlsx"
    )
