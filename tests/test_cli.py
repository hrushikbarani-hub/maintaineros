from maintaineros.cli import main
from maintaineros.models import RepositorySnapshot
from maintaineros.storage import Store


def test_cli_can_report_without_network(tmp_path, capsys):
    path = tmp_path / "db"
    Store(path).save(RepositorySnapshot(full_name="team/project"))
    assert main(["report", "--db", str(path), "--format", "json"]) == 0
    assert '"repository": "team/project"' in capsys.readouterr().out


def test_cli_rejects_invalid_name_before_network(capsys):
    assert main(["scan", "https://evil.invalid/x"]) == 2
    assert "String should match pattern" in capsys.readouterr().err


def test_cli_can_set_policy_before_first_capture(tmp_path, capsys):
    path = str(tmp_path / "db")
    assert (
        main(["policy", "team/project", "--db", path, "--stale-days", "45", "--no-check-releases"])
        == 0
    )
    capsys.readouterr()
    assert main(["policy", "team/project", "--db", path]) == 0
    result = capsys.readouterr().out
    assert '"stale_days": 45' in result and '"check_releases": false' in result
    assert main(["policy", "team/project", "--db", path, "--stale-days", "0"]) == 2
