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
