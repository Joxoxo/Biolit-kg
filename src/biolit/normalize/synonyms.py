"""M3 第 2 步：用同义词表把各种写法映射到标准名。"""
import yaml

from biolit.db import ROOT
from biolit.normalize.clean import basic_clean


class Normalizer:
    def __init__(self, path=ROOT / "configs" / "synonyms.yaml"):
        cfg = yaml.safe_load(open(path, encoding="utf-8"))
        # 建一个"写法 → 标准名"的查找表；标准名自己也映射到自己
        self.lookup = {}
        for canonical, variants in cfg["synonyms"].items():
            self.lookup[basic_clean(canonical)] = canonical
            for v in variants:
                self.lookup[basic_clean(v)] = canonical
        self.hierarchy = cfg.get("hierarchy", {})

    def __call__(self, name):
        """先基础清洗，再查同义词表；查不到就保留清洗后的写法。"""
        cleaned = basic_clean(name)
        if cleaned is None:
            return None
        return self.lookup.get(cleaned, cleaned)
