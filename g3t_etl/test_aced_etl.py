from uuid import UUID

import pytest
from pydantic import ValidationError

from g3t_etl import IdMinter, TransformerHelper


def test_transformer_helper_init():
    """Should raise exception if not project_id is not provided."""
    with pytest.raises(ValidationError):
        _ = IdMinter()

    with pytest.raises(ValidationError):
        _ = IdMinter(project_id='abc')

    _ = IdMinter(project_id='abc-123')


def test_transformer_helper_idempotent():
    helper_default = TransformerHelper(project_id='abc-123')
    assert helper_default.system.endswith('/abc-123')
    assert helper_default.namespace == UUID('f500b28c-73b4-3571-a7cc-dbf35a4b950b')
    helper_default_ns = TransformerHelper(project_id='abc-123', namespace="example.com")
    assert helper_default_ns.system.endswith('/abc-123')
    assert helper_default_ns.namespace == UUID('9073926b-929f-31c2-abc9-fad77ae3e8eb')

    id_default = helper_default.mint_id(helper_default.populate_identifier('123', 'http://example.com'), resource_type='Patient')
    id_ns = helper_default_ns.mint_id(helper_default.populate_identifier('123', 'http://example.com'), resource_type='Patient')
    assert id_default != id_ns
