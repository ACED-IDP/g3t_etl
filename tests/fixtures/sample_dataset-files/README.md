# Transient test data
Files in this folder are not checked into the repository due to file sizes. They are used for testing and development purposes only.

## Dummy file generation

The process is used to generate synthetic data for testing and development purposes. The module is not intended for use in production environments.


```
cd tests/fixtures/IDP_UCL_VS_dataset-files

DUMMY_DATA_DIR=dummy_data_30pid
# repeat for:
# dummy_data_200pid
# dummy_data_500pid

SPECIMENS=../IDP_UCL_VS_dataset-FHIR/$DUMMY_DATA_DIR/Specimen.ndjson
cat $SPECIMENS | jq -r '.identifier[0].value' | xargs -L 1 -I SPECIMEN cp  ANY_mri_guided_prostate_biopsy.jpeg $DUMMY_DATA_DIR/SPECIMEN_mri_guided_prostate_biopsy.jpeg


```
