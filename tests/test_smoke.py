import docs_to_ledger


def test_import() -> None:
    assert hasattr(docs_to_ledger, "__version__")
    assert isinstance(docs_to_ledger.__version__, str)
