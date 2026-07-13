from pathlib import Path

from scripts.reset_demo_data import DEFAULT_DEMO_USERS, discover_demo_documents, parse_args


def test_discover_demo_documents_uses_curated_titles():
    documents = discover_demo_documents(Path("data/test_uploads"))
    titles = {document.title for document in documents}

    assert len(documents) == 8
    assert "现行客户数据导出制度" in titles
    assert "安全事件响应流程" in titles


def test_parse_args_defaults_to_safe_dry_run(monkeypatch):
    monkeypatch.setattr("sys.argv", ["reset_demo_data.py"])

    args = parse_args()

    assert args.apply is False
    assert args.clear_audit is True
    assert args.clear_all_documents is True
    assert args.seed_documents is True
    assert args.users is None


def test_parse_args_all_expands_reset_actions(monkeypatch):
    monkeypatch.setattr("sys.argv", ["reset_demo_data.py", "--all", "--apply"])

    args = parse_args()

    assert args.apply is True
    assert args.clear_audit is True
    assert args.clear_all_documents is True
    assert args.seed_documents is True
    assert DEFAULT_DEMO_USERS == ["local-demo", "demo-alice", "demo-bob"]
