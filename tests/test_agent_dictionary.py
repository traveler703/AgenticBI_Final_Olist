from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_data_analyst_knows_review_views() -> None:
    source = (ROOT / "agents" / "data_analyst.py").read_text(encoding="utf-8")
    assert "mv_review_quality" in source
    assert "mv_seller_review_risk" in source
    assert "不允许引用 total_orders" not in source


def test_yaml_dictionary_lists_review_views() -> None:
    dictionary = (ROOT / "config" / "data_dictionary.yaml").read_text(encoding="utf-8")
    assert "mv_review_quality" in dictionary
    assert "mv_seller_review_risk" in dictionary
    assert "total_orders" in dictionary

