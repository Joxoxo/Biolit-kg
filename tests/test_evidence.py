"""证据核验：模型给的证据句是否真的出自原文。"""
from biolit.normalize.evidence import check_evidence

SOURCE = ("Apixaban was associated with a lower risk of major bleeding (HR 0.61; 95% CI 0.52–0.71; p ≤ 0.001). "
          "All-cause mortality did not differ (p = 0.031).")


def test_exact_sentence_is_verified():
    ev = "Apixaban was associated with a lower risk of major bleeding (HR 0.61; 95% CI 0.52–0.71; p ≤ 0.001)."
    assert check_evidence(ev, SOURCE)[0] == "verified"


def test_symbol_variants_are_still_verified():
    # 模型常把 ≤ 写成 <=、把 en dash 写成连字符，这不算改写
    ev = "Apixaban was associated with a lower risk of major bleeding (HR 0.61; 95% CI 0.52-0.71; p <= 0.001)."
    assert check_evidence(ev, SOURCE)[0] == "verified"


def test_case_and_whitespace_ignored():
    ev = "APIXABAN was   associated with a lower risk of MAJOR bleeding"
    assert check_evidence(ev, SOURCE)[0] == "verified"


def test_changed_number_is_caught():
    # 其余文字都对，只把 p 值抄错 —— 覆盖率很高，但数字核对必须把它抓出来
    ev = "All-cause mortality did not differ (p = 0.398)."
    assert check_evidence(ev, SOURCE)[0] == "unverified"


def test_fabricated_sentence_is_unverified():
    ev = "Rivaroxaban doubled the risk of intracranial hemorrhage in elderly patients."
    status, score = check_evidence(ev, SOURCE)
    assert status == "unverified"
    assert score < 0.9
