
![](docs/g3t_etl-logo.png)
# g3t_etl

## Transforming Research Data to FHIR


## Use case

Measurements ([Observations](https://build.fhir.org/observation.html#10.1.1)) are a central element in healthcare, used to support diagnosis, monitor progress, determine baselines and patterns and even capture demographic characteristics, as well as capture results of tests performed on products and substances.

As a `ACED data contributor`, I have a rich set of measurements that I need to associate with several possible resources [Patient, Specimen, Procedure, Condition, etc.]

These Observations are stored in a csv file and I need to transform them into FHIR resources.

> Note: For other use cases, without a rich set of measurements, see the [adding metadata workflow](https://aced-idp.github.io/workflows/metadata/#create-metadata-files) in the ACED documentation.

### Project Overview
This project implements an the `Transform` step of the ETL (Extract, Transform, Load) pipeline for processing research into a FHIR resources.
It provides framework with robust command-line and plugin architecture. It empowers users to process diverse data, apply custom transformations, and load it into target destinations.


### Transformers

Core framework provides foundational transformations (e.g., normalization, validation, and graph construction).
Users can develop custom transformers as plugins for unique needs.

To use this project, please refer to the [project documentation](user-guide.md) for detailed instructions on how to use the project.


### Contributing
This project is open to contributions from the research community. If you are interested in contributing to the project, please contact the project team.
See the [contributing guide](CONTRIBUTING.md) for more information on how to contribute to the project.
