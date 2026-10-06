from prefect.testing.utilities import prefect_test_harness
from starter_canary.flows import canary


def test_canary_runs_locally():
    with prefect_test_harness():
        result = canary(greeting="test")
    assert result["greeting"] == "test"
    assert result["deployment"].startswith("(none")
