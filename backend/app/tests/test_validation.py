from app.core.validation import validate_coder_response
from app.schemas.A2A import CoderToWriter


def test_validation_requires_execution_and_report():
    valid = CoderToWriter(success=True, executed_code=True, code_response="RMSE=0.2")
    no_code = CoderToWriter(success=True, executed_code=False, code_response="done")
    no_report = CoderToWriter(success=True, executed_code=True, code_response="")

    assert validate_coder_response(valid)[0] is True
    assert validate_coder_response(no_code)[0] is False
    assert validate_coder_response(no_report)[0] is False
