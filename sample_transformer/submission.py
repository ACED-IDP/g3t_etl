# generated by datamodel-codegen:
#   filename:  submission.schema.json
#   timestamp: 2024-04-06T13:17:41+00:00

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Submission(BaseModel):
    id: Optional[str] = Field(
        None,
        description='Patient ID',
        json_schema_extra={'csv_type_notes': 'See notes'},
    )
    align: Optional[str] = Field(
        None,
        description='Aligned lesion',
        json_schema_extra={
            'csv_type_notes': 'Binary',
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Condition',
        },
    )
    ageDiagM: Optional[int] = Field(
        None,
        description='Age at Diagnosis in Months',
        json_schema_extra={
            'fhir_resource_type': 'Condition.age',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mo',
            'uom_unit': 'month',
        },
    )
    ageDiagY: Optional[int] = Field(
        None,
        description='Age at Diagnosis in Years',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'https://loinc.org/',
            'coding_code': '63932-8',
            'coding_display': 'Age at diagnosis',
            'observation_subject': 'Condition',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': '/ a',
            'uom_unit': '/ year',
        },
    )
    ppsa: Optional[float] = Field(
        None,
        description='Presenting PSA at diagnosis',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct/',
            'coding_code': '63476009',
            'coding_display': 'Prostate specific antigen measurement',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'ng/mL',
            'uom_unit': 'nanograms per milliliter (ng/mL)',
        },
    )
    BxPreDiag: Optional[int] = Field(
        None,
        description='Biopsy before diagnosis',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    psaBx: Optional[float] = Field(
        None,
        description='PSA at Biopsy A or B',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct/',
            'coding_code': '63476009',
            'coding_display': 'Prostate specific antigen measurement',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'ng/mL',
            'uom_unit': 'nanograms per milliliter (ng/mL)',
        },
    )
    months_diag: Optional[int] = Field(
        None,
        alias='months.diag',
        description='Months that elapsed since prostate cancer diagnosis',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mo',
            'uom_unit': 'month',
        },
    )
    gleason: Optional[str] = Field(
        None,
        description='Gleason grade',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct',
            'coding_code': 372278000,
            'coding_display': 'Gleason score',
            'observation_subject': 'Procedure',
        },
    )
    mccl: Optional[int] = Field(
        None,
        description='Maximum Cancer Core Length in mm',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct',
            'coding_code': '399598003',
            'coding_display': 'Length of core in specimen obtained by needle biopsy',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'millimeter',
            'uom_unit': 'mm',
        },
    )
    ucl: Optional[str] = Field(
        None,
        description='UCL Definition',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    prvol: Optional[float] = Field(
        None,
        description='Prostate volume on MRI',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'https://loinc.org/',
            'coding_code': '15325-4',
            'coding_display': 'Prostate specific Ag/Prostate volume calculated',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mL',
            'uom_unit': 'milliliter',
        },
    )
    side: Optional[str] = Field(
        None,
        description='Sampled area side (Left or Right)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    zone: Optional[str] = Field(
        None,
        description='Sampled area zone (Peripheral, Transition, Both)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    loc: Optional[str] = Field(
        None,
        description='Sampled area location (Posterior, Anterior or combinations)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    level: Optional[str] = Field(
        None,
        description='Sampled area level (Base, Mid-gland, Apex or combinations)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    likert: Optional[int] = Field(
        None,
        description='Likert score of sampled MRI area',
        json_schema_extra={
            'csv_type_notes': '2024-05-01T00:00:00',
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct/',
            'coding_code': 273575009,
            'coding_display': 'ikert scale (assessment scale}',
            'observation_subject': 'Procedure',
        },
    )
    pirads: Optional[int] = Field(
        None,
        description='PI-RADSv2 score of sampled MRI area',
        json_schema_extra={
            'csv_type_notes': '2024-05-01T00:00:00',
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://dicom.nema.org/resources/ontology/DCM/',
            'coding_code': '130564',
            'coding_display': 'PI-RADS v2.0',
            'observation_subject': 'Procedure',
        },
    )
    precise: Optional[int] = Field(
        None,
        description='PRECISE score of sampled MRI area (only for timepoint B)',
        json_schema_extra={
            'csv_type_notes': '2024-05-01T00:00:00',
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    adcMean: Optional[float] = Field(
        None,
        description='Mean apparent diffusion coefficient of sampled MRI area',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct',
            'coding_code': '46638006',
            'coding_display': 'Diffusion',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'm2/s',
            'uom_unit': 'square meters per second',
        },
    )
    adcn: Optional[float] = Field(
        None,
        description='Mean apparent diffusion coefficient of sampled MRI area (normalised by contralateral benign prostate ADC)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'm2/s',
            'uom_unit': 'square meters per second',
        },
    )
    adcu: Optional[float] = Field(
        None,
        description='Mean apparent diffusion coefficient of sampled MRI area (normalised by urine ADC)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'm2/s',
            'uom_unit': 'square meters per second',
        },
    )
    focality: Optional[str] = Field(
        None,
        description='Lesion focality',
        json_schema_extra={
            'csv_type_notes': 'Binary',
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    best: Optional[str] = Field(
        None,
        description='MRI sequence on which lesion is best seen',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct/',
            'coding_code': '396199003',
            'coding_display': 'Tumour focality',
            'observation_subject': 'Procedure',
        },
    )
    bestVol: Optional[float] = Field(
        None,
        description='Volume of lesion on best sequence (ml)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mL',
            'uom_unit': 'milliliter',
        },
    )
    t2Vol: Optional[float] = Field(
        None,
        description='Lesion volume on T2 (ml)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mL',
            'uom_unit': 'milliliter',
        },
    )
    Epi_Count: Optional[int] = Field(
        None,
        description='Total number of epithelial cells within all tissue areas on H&E',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct/',
            'coding_code': '393942000',
            'coding_display': 'Epithelial cell count',
            'observation_subject': 'Procedure',
        },
    )
    Stroma_Count: Optional[int] = Field(
        None,
        description='Total number of stromal cells within all tissue areas on H&E',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct/',
            'coding_code': '74765001',
            'coding_display': 'Lymphocyte',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mL',
            'uom_unit': 'milliliter',
        },
    )
    Lymphocyte_Count: Optional[int] = Field(
        None,
        description='Total number of lymphocytes within all tissue areas on H&E',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct/',
            'coding_code': '271036002',
            'coding_display': 'Lymphocyte percent differential count',
            'observation_subject': 'Procedure',
        },
    )
    Lymphocyte_Percentage: Optional[float] = Field(
        None,
        description='% of lymphocytes within all tissue areas on H&E',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    Irani_Gscore: Optional[int] = Field(
        None,
        description='Irani score (number of lymphocytes in largest inflammatory cluster)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    Tissue_Area: Optional[float] = Field(
        None,
        description='Tissue area (square mm)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Epithelial_Area: Optional[float] = Field(
        None,
        description='Epithelial area (square mm)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Stromal_Area: Optional[float] = Field(
        None,
        description='Stromal area (square mm)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Inflammatory_Area: Optional[float] = Field(
        None,
        description='Inflammation area (square mm)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Epithelial_Area_Percentage: Optional[float] = Field(
        None,
        description='% epithelial area (epithelial area fraction)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    Stromal_Area_Percentage: Optional[float] = Field(
        None,
        description='% stromal area (stromal area fraction)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    Inflammatory_Area_Percentage: Optional[float] = Field(
        None,
        description='% inflammation area (inflammation area fraction)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
    Epithelial_Stromal_Ratio: Optional[float] = Field(
        None,
        description='Epithelial area/Stromal area (square mm)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Lumen_Area: Optional[float] = Field(
        None,
        description='Total area detected as lumen within all tissue areas (square mm)',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Lumen_Density: Optional[float] = Field(
        None,
        description='Lumen area/tissue area',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Lumen_Density_Gland: Optional[float] = Field(
        None,
        description='Lumen area/epithelial area',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Annotated_Cancer_Area: Optional[float] = Field(
        None,
        description='Total area of cancer annotated by pathologist',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Normal_Area: Optional[float] = Field(
        None,
        description='Area classified as normal by classifier',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    PIN_Area: Optional[float] = Field(
        None,
        description='Area classified as PIN by classifier',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Gleason_3_Area: Optional[float] = Field(
        None,
        description='Area classified as G3 by classifier',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Gleason_4_Area: Optional[float] = Field(
        None,
        description='Area classified as G4 by classifier',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Gleason_5_Area: Optional[float] = Field(
        None,
        description='Area classified as G5 or higher by classifier',
        json_schema_extra={
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
            'uom_system': 'http://unitsofmeasure.org',
            'uom_code': 'mm2',
            'uom_unit': 'square millimeter',
        },
    )
    Gleason_Primary: Optional[int] = Field(
        None,
        description='Primary Gleason according to classifier',
        json_schema_extra={
            'csv_type_notes': 'Ordinal',
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct',
            'coding_code': 372278000,
            'coding_display': 'Gleason score',
            'observation_subject': 'Procedure',
        },
    )
    Gleason_Secondary: Optional[int] = Field(
        None,
        description='Secondary Gleason according to classifier',
        json_schema_extra={
            'csv_type_notes': 'Ordinal',
            'fhir_resource_type': 'Observation',
            'coding_system': 'http://snomed.info/sct',
            'coding_code': 372278000,
            'coding_display': 'Gleason score',
            'observation_subject': 'Procedure',
        },
    )
    Grade_Group: Optional[int] = Field(
        None,
        description='Grade Group according to classifier',
        json_schema_extra={
            'csv_type_notes': 'Ordinal',
            'fhir_resource_type': 'Observation',
            'observation_subject': 'Procedure',
        },
    )
