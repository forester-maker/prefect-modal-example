from starter_common import run_scoped_prefix


def test_override_wins():
    assert run_scoped_prefix("s3://b/out", override="s3://b/fixed/") == "s3://b/fixed"


def test_outside_a_run_is_still_unique_and_under_base():
    p = run_scoped_prefix("/tmp/outputs/")
    assert p.startswith("/tmp/outputs/adhoc/")
    assert len(p.split("/")) == 6  # base(3) + name + day + time
