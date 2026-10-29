"""M3 第 1 步：基础清洗。把同一个词的不同"写法"统一，不涉及医学判断。

例：" Major  Haemorrhage. " → "major hemorrhage"
"""
import re

# 英式拼写 → 美式拼写（医学文献里最常见的几组）
UK_TO_US = {
    "haemorrhage": "hemorrhage",
    "haemorrhagic": "hemorrhagic",
    "haematoma": "hematoma",
    "haemoglobin": "hemoglobin",
    "ischaemic": "ischemic",
    "ischaemia": "ischemia",
    "anaemia": "anemia",
    "oesophageal": "esophageal",
    "oedema": "edema",
    "paediatric": "pediatric",
    "haemodialysis": "hemodialysis",
    "foetal": "fetal",
}

# 括号里的缩写，如 "stroke and systemic embolism (SSE)" 里的 "(SSE)"
PAREN_ABBR = re.compile(r"\s*\(([A-Za-z0-9\-/]{1,10})\)\s*$")


def basic_clean(name: str | None) -> str | None:
    if name is None:
        return None
    s = name.strip().strip(".,;:")
    s = PAREN_ABBR.sub("", s)               # 去掉末尾括号里的缩写
    s = s.lower()
    s = re.sub(r"\s+", " ", s)               # 多个空格 → 一个
    s = re.sub(r"\s*/\s*", "/", s)           # "stroke / SE" → "stroke/se"
    for uk, us in UK_TO_US.items():
        s = re.sub(rf"\b{uk}\b", us, s)
    return s or None


if __name__ == "__main__":
    for x in [" Major  Haemorrhage. ", "stroke and systemic embolism (SSE)",
              "Ischaemic stroke", "stroke / systemic embolism"]:
        print(f"{x!r:45} → {basic_clean(x)!r}")
