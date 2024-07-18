import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape


@pytest.fixture
def template_env() -> str:
    template_dir = 'tests/fixtures/templates'
    return Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape())


@pytest.fixture
def simple_patient(template_env) -> dict:
    """Transform a patient from a template."""
    # load the template
    template = template_env.get_template('Patient.yaml.jinja')
    # render the template
    yaml_source = template.render(sex='male')
    # load the yaml from a string
    patient = yaml.safe_load(yaml_source)
    return patient
