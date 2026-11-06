"""抽取评估的指标计算。"""
import pytest

from biolit.eval.score import prf, score


def test_prf():
    m = prf(correct=8, extracted=10, missed=2)
    assert m["precision"] == pytest.approx(0.8)
    assert m["recall"] == pytest.approx(0.8)
    assert m["f1"] == pytest.approx(0.8)


def test_prf_handles_zero():
    assert prf(0, 0, 0)["f1"] == 0.0


PAPERS = [{"pmid": 1, "study_type": "rct", "missed": [{"relation": "x", "note": ""}],
           "model": [{"relation": "a", "judge": "正确", "note": ""},
                     {"relation": "b", "judge": "部分正确", "note": ""},
                     {"relation": "c", "judge": "错误", "note": ""}]}]


def test_lenient_counts_partial_as_correct():
    m = score(PAPERS, lenient=True)
    assert (m["correct"], m["extracted"], m["missed"]) == (2, 3, 1)


def test_strict_counts_partial_as_missed():
    # 严格口径："部分正确"不算对，而且那条正确关系没有被准确抽到，所以同时算一次漏抽
    m = score(PAPERS, lenient=False)
    assert (m["correct"], m["extracted"], m["missed"]) == (1, 3, 2)
