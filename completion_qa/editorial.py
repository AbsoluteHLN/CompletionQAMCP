"""Deterministic, local suggestions; not semantic or model-based editing."""
import difflib
import re
from typing import Protocol

PROFILES = ("short_reply", "academic", "technical_report")

class Reviewer(Protocol):
    """Optional in-process interface. No remote implementation is shipped."""
    def review(self, text: str, profile: str) -> dict: ...

class DisabledReviewer:
    def review(self, text: str, profile: str) -> dict:
        return {"status": "blocked", "reason": "No model configured; no text transmitted"}

def diagnose(text: str, profile: str) -> dict:
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    if len(text) > 200_000:
        raise ValueError("Text too large")
    findings = []
    proposed = text
    replacements = {"综上所述，可以看出，": "综上，", "值得注意的是，": ""}
    if profile == "short_reply":
        replacements.update({"我完全理解您的需求。": "", "希望以上内容对您有所帮助。": ""})
        if len(text) > 180:
            findings.append({"rule": "reply_length", "severity": "advisory", "message": "回复较长；检查能否先给结论，再保留必要细节。"})
    if profile == "academic":
        for phrase in ("毫无疑问", "完全证明", "显然优于", "并不意味着", "不能排除"):
            if phrase in text:
                findings.append({"rule": "claim_calibration", "severity": "advisory", "message": f"核对“{phrase}”是否与证据强度相符；不要机械删除必要限定。"})
    if profile == "technical_report":
        for phrase in ("全部通过", "完整验证", "生产可用"):
            if phrase in text:
                findings.append({"rule": "verification_scope", "severity": "advisory", "message": f"“{phrase}”应附验证范围与未执行项，避免以局部测试代表全覆盖。"})
    if profile == "academic":
        for phrase in ("可能在一定程度上或许", "并非否定", "也不是说"):
            if phrase in text:
                findings.append({"rule": "hedge_stack_or_defense", "severity": "advisory", "message": f"检查“{phrase}”是否重复限定或回应了并不存在的争议；保留必要研究边界。"})
    # Only propose deletion at unquoted prose line starts. Never rewrite inside
    # code spans/fences, quotation lines, citations or arbitrary substrings.
    lines = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            lines.append(line)
            continue
        if not in_fence and "`" not in line:
            for before, after in replacements.items():
                if line.startswith(before):
                    findings.append({"rule": "filler", "severity": "advisory", "message": f"可审阅精简：{before}"})
                    line = after + line[len(before):]
                    break
        lines.append(line)
    proposed = "".join(lines)
    # Conservative v0.1 protection: mixed prose, quotations and code require
    # a real parser/human review; do not propose any rewrite for that input.
    if any(marker in text for marker in ('"', "'", "“", "”", "‘", "’", "`", "~~~")):
        proposed = text
        findings.append({"rule": "protected_mixed_content", "severity": "advisory", "message": "含引语或代码标记，仅诊断；不提出自动改写。"})
    return {"status": "pass", "method": "deterministic_heuristic", "profile": profile,
            "findings": findings, "proposed_text": proposed,
            "patch": "".join(difflib.unified_diff([line + "\n" for line in text.splitlines()], [line + "\n" for line in proposed.splitlines()], fromfile="original", tofile="proposed")),
            "applied": False, "scope": "Rule execution only; not editorial approval or factual verification"}
