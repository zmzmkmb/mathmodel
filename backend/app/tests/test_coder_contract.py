from app.schemas.A2A import CoderToWriter


def test_coder_contract_carries_validation_failure():
    result = CoderToWriter(
        success=False,
        error_message="ValueError: invalid dimension",
        attempts=3,
    )

    assert not result.success
    assert result.error_message == "ValueError: invalid dimension"
    assert result.attempts == 3
