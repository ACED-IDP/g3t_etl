from typing import NamedTuple

import yaml
from fhir.resources.patient import Patient
from jinja2 import Environment, BaseLoader


def test_translator():

    # mock translator
    class Transformer(NamedTuple):
        sex: str

        def normalise_sex(self):
            if self.sex in ['male', 'female']:
                return self.sex
            if self.sex.lower() == 'm':
                return 'male'
            if self.sex.lower() == 'f':
                return 'female'

    # create template from string
    template = Environment(loader=BaseLoader).from_string(
        """
            resourceType: Patient
            active: true
            gender: {{ translator.sex }}  # from translator
            birthDate:  {{ translator.birthDate }}  # from translator (not implemented), gets set to None
        """
    )

    _ = template.render(**{'translator': Transformer(sex='male')})
    print(_)
    simple_patient = yaml.safe_load(_)
    patient = Patient(**simple_patient)
    assert patient, f"Could not create patient from {simple_patient}"
    assert Patient.validate(patient), f"Patient did not validate {patient}"
    assert patient.birthDate is None, f"Expected birthDate to be None {patient.birthDate}"
    assert patient.gender == 'male', f"Expected gender to be male {patient.gender}"

    # create template from string
    template = Environment(loader=BaseLoader).from_string(
        """
            resourceType: Patient
            active: true
            gender: {{ transformer.normalise_sex() }}  # from translator
            birthDate:  {{ transformer.birthDate }}  # from translator (not implemented), gets set to None
        """
    )

    _ = template.render(**{'transformer': Transformer(sex='M')})
    print(_)
    simple_patient = yaml.safe_load(_)
    patient = Patient(**simple_patient)
    assert patient, f"Could not create patient from {simple_patient}"
    assert Patient.validate(patient), f"Patient did not validate {patient}"
    assert patient.birthDate is None, f"Expected birthDate to be None {patient.birthDate}"
    assert patient.gender == 'male', f"Expected gender to be male {patient.gender}"
