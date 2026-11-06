// 说明书比对状态 → 网页上显示的标签和颜色（结合人工审核结果）
import type { Mechanism } from "@/lib/api";

export interface Status {
  key: "conflict" | "signal" | "covered" | "error" | "unreviewed" | "none";
  label: string;
  color: string;
}

export function mechStatus(m: Mechanism): Status {
  if (m.review === "抽取错误") return { key: "error", label: "抽取错误", color: "#adb5bd" };
  if (m.review === "真信号" && m.label_status === "说明书不一致")
    return { key: "conflict", label: "与说明书冲突", color: "#b45309" };
  if (m.review === "真信号") return { key: "signal", label: "潜在信号（说明书未涵盖）", color: "#c2271a" };
  if (m.review === "说明书其实有") return { key: "covered", label: "说明书已涵盖", color: "#047857" };
  switch (m.label_status) {
    case "说明书已收录":
    case "类别收录":
    case "上位概念收录":
    case "原文提及（抽取遗漏）":
      return { key: "covered", label: "说明书已涵盖", color: "#047857" };
    case "说明书不一致":
    case "仅文献报道":
      return { key: "unreviewed", label: "说明书未收录（未审核）", color: "#868e96" };
    default:
      return { key: "none", label: "未比对", color: "#ced4da" };
  }
}
