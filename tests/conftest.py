import pytest


@pytest.fixture
def expected_keys():
    """"""
    return ['Annotated_Cancer_Area', 'BxPreDiag', 'Epi_Count', 'Epithelial_Area', 'Epithelial_Area_Percentage',
            'Epithelial_Stromal_Ratio', 'Gleason_3_Area', 'Gleason_4_Area', 'Gleason_5_Area',
            'Gleason_Primary', 'Gleason_Secondary', 'Grade_Group', 'Inflammatory_Area',
            'Inflammatory_Area_Percentage', 'Irani_Gscore', 'Lumen_Area', 'Lumen_Density',
            'Lumen_Density_Gland', 'Lymphocyte_Count', 'Lymphocyte_Percentage', 'Normal_Area', 'PIN_Area',
            'Stroma_Count', 'Stromal_Area', 'Stromal_Area_Percentage', 'Tissue_Area', 'adcMean', 'adcn',
            'adcu', 'ageDiagM', 'ageDiagY', 'align', 'best', 'bestVol', 'focality', 'gleason', 'id', 'level',
            'likert', 'loc', 'mccl', 'months.diag', 'pirads', 'ppsa', 'precise', 'prvol', 'psaBx', 'side',
            't2Vol', 'ucl', 'zone']
