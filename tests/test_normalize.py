"""实体标准化：基础清洗 + 同义词表。"""
from biolit.normalize.clean import basic_clean
from biolit.normalize.synonyms import Normalizer

norm = Normalizer()


def test_basic_clean():
    assert basic_clean(" Major  Haemorrhage. ") == "major hemorrhage"          # 空格、标点、英式拼写
    assert basic_clean("stroke and systemic embolism (SSE)") == "stroke and systemic embolism"
    assert basic_clean("stroke / SE") == "stroke/se"
    assert basic_clean(None) is None


def test_brand_names_map_to_generic():
    assert norm("Eliquis") == "apixaban"
    assert norm("Xarelto") == "rivaroxaban"
    assert norm("dabigatran etexilate") == "dabigatran"


def test_abbreviations_map_to_canonical():
    assert norm("GI bleeding") == "gastrointestinal bleeding"
    assert norm("ICH") == "intracranial hemorrhage"
    assert norm("NOACs") == "doac"
    assert norm("P-glycoprotein") == "p-gp"


def test_unknown_name_is_kept_after_cleaning():
    assert norm("  Some New Drug ") == "some new drug"


def test_hierarchy_is_loaded():
    assert "doac" in norm.hierarchy["apixaban"]
    assert "bleeding" in norm.hierarchy["gastrointestinal bleeding"]
