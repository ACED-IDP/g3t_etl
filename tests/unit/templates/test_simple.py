from fhir.resources.patient import Patient


def test_simple_transform(simple_patient):
    """Create a patient dict from a template."""
    # assert success
    print(simple_patient)
    assert simple_patient['gender'] == 'male', f"Expected gender not found {simple_patient['gender']}"


def test_simple_load(simple_patient):
    """Create a FHIR.patient from a template."""
    patient = Patient(**simple_patient)
    assert patient, f"Could not create patient from {simple_patient}"
    assert Patient.validate(patient), f"Patient did not validate {patient}"
