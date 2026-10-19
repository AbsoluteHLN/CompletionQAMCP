"""Deterministic, review-only Chinese/English editorial assistance.

Offsets are Python Unicode code-point offsets, with exclusive end positions.
This module never invokes a model, writes a document, or verifies truth.
"""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re

PROFILES = ("conversation_summary", "technical_document", "academic")
MAX_TEXT_LENGTH = 200_000

_PHRASES = (
    ("进行分析", "分析", "可改用直接动词；确认与原意一致后再采用。"),
    ("进行研究", "研究", "可简化动词结构；研究方法和范围应保留。"),
    ("在一定程度上", None, "说明程度或依据；若表达真实不确定性，应保留而非直接删除。"),
    ("众所周知", None, "补充依据或删除空泛引导语，不能把常识措辞当作证据。"),
    ("毋庸置疑", None, "核对证据是否支持如此确定的语气。"),
    ("总而言之", None, "检查是否重复已有总结；结论本身必须保留。"),
    ("非常重要", None, "尽量指出具体影响或验收标准，避免仅作程度评价。"),
    ("进一步提升", None, "明确提升对象、基线和衡量方式；缺失数据不要补造。"),
)
_NUMBERS = re.compile(r"(?<![\w])[-+−]?\d+(?:[.,]\d+)*(?:\s*(?:%|％|‰))?|\d+(?:[.,]\d+)*(?:%|％|‰)?")
_CITATIONS = re.compile(r"\[(?:\d+[\d,，;；–—\-\s]*)\]|【[^】\n]+】|\([^()\n]*\b(?:19|20)\d{2}[a-z]?[^()\n]*\)|https?://[^\s<>\]\)]+|doi:\s*\S+", re.I)
_QUANTITIES = re.compile(r"[-+−]?\d+(?:[.,]\d+)*(?:\s*)(?:mmol/L|mg/kg|μg|µg|mg|kg|mL|ml|cm|mm|ms|kPa|MPa|°C|℃|%|％|秒|分钟|小时|个月|天|例|人|克|毫升|米)(?![A-Za-z])")
_FORMULAS = re.compile(r"\$\$[\s\S]*?\$\$|(?<!\\)\$(?:\\.|[^$\n])*?\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]")
_MARKERS = {
    "negation": re.compile(r"未能|未发现|未观察到|不能|不足以|不支持|无显著|没有|并非|不|未|无|\b(?:not|no|never|without)\b", re.I),
    "limitations": re.compile(r"可能|尚需|尚待|仅限|仅|局限|限制|不确定|样本量|相关性|不能推断|不可推断|\b(?:may|might|limitation[s]?|uncertain|correlation|preliminary)\b", re.I),
    "causality": re.compile(r"导致|因果|因此|从而|归因|引起|\b(?:cause[s]?|causal|therefore|result[s]? in)\b", re.I),
    "conclusions": re.compile(r"结论|表明|说明|证实|证明|提示|\b(?:conclude[s]?|conclusion[s]?|demonstrate[s]?|prove[s]?|suggest[s]?)\b", re.I),
}


def _span(start: int, end: int, text: str) -> dict:
    return {"start": start, "end": end, "text": text[start:end]}


def _changes(original: str, candidate: str) -> list[dict]:
    # Bound worst-case repeated-text matching; large reviews use one exact
    # changed region rather than promising a minimal character-level diff.
    if len(original) + len(candidate) > 20_000:
        start = 0
        limit = min(len(original), len(candidate))
        while start < limit and original[start] == candidate[start]:
            start += 1
        a, b = len(original), len(candidate)
        while a > start and b > start and original[a - 1] == candidate[b - 1]:
            a -= 1
            b -= 1
        return [{"operation": "replace" if a > start and b > start else ("delete" if a > start else "insert"),
                 "original": _span(start, a, original), "candidate": _span(start, b, candidate)}]
    return [
        {"operation": op, "original": _span(a, b, original),
         "candidate": _span(c, d, candidate)}
        for op, a, b, c, d in SequenceMatcher(None, original, candidate, autojunk=False).get_opcodes()
        if op != "equal"
    ]


def _protected_ranges(text: str) -> list[tuple[int, int]]:
    # Do not suggest prose edits inside fenced/inline code, URLs or citations.
    pattern = r"```[\s\S]*?(?:```|\Z)|~~~[\s\S]*?(?:~~~|\Z)|`[^`\n]*`"
    ranges = [(m.start(), m.end()) for m in re.finditer(pattern, text)]
    ranges.extend((m.start(), m.end()) for m in _CITATIONS.finditer(text))
    ranges.extend((m.start(), m.end()) for m in _FORMULAS.finditer(text))
    return ranges


def _sentences(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"[^。！？!?\n]+[。！？!?]?", text) if m.group().strip()]


def _structure(text: str, profile: str) -> list[dict]:
    checks = {
        "conversation_summary": (
            ("decision", r"决定|确认|结论|已选|decision|agreed", "说明已确认的决定，并与待定建议区分。"),
            ("next_action", r"下一步|待办|后续|负责|next step|action item", "列明下一步、负责人和时间；原文没有的信息标为待确认。"),
            ("open_questions", r"待确认|待定|未解决|阻塞|暂无待定|open question|blocker", "注明尚未解决的问题或明确无待定项，不凭空新增承诺。"),
        ),
        "technical_document": (
            ("scope", r"目标|范围|目的|scope|objective", "交代目标、适用范围和边界。"),
            ("procedure", r"步骤|实现|接口|方法|操作|procedure|implementation|interface", "补充可执行步骤或接口输入输出说明。"),
            ("acceptance", r"验收|测试|验证|预期|acceptance|test|expected", "列明可观察的验收结果和检查方法。"),
            ("failure", r"失败|异常|错误|回退|限制|error|failure|rollback|limitation", "说明失败条件、限制或回退方式。"),
        ),
        "academic": (
            ("question", r"目的|问题|假设|研究|objective|hypothesis|question", "明确研究问题或假设。"),
            ("method", r"方法|样本|实验|数据|method|sample|experiment", "交代方法、样本或数据来源。"),
            ("result", r"结果|发现|观察|result|finding", "区分观察结果与解释，不补造结果。"),
            ("limitation", r"局限|限制|可能|尚需|不能推断|limitation|uncertain|may|might", "检查必要限制是否交代；没有局限词不等于研究没有局限。"),
        ),
    }
    return [{"code": "structure_" + name, "severity": "suggestion", "message": message,
             "basis": "keyword_heuristic", "requires_human_review": True}
            for name, pattern, message in checks[profile] if not re.search(pattern, text, re.I)]


def review(text: str, profile: str, candidate: str | None = None) -> dict:
    """Return suggestions and an auditable comparison, never apply a rewrite.

    If no candidate is supplied, the original is retained exactly. A caller may
    submit a proposed rewrite for review. Only exact CRLF-to-LF normalization
    is classified as a permitted mechanical transformation, not fact checking.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("unknown editorial profile")
    if candidate is not None and not isinstance(candidate, str):
        raise TypeError("candidate must be a string or None")
    if len(text) > MAX_TEXT_LENGTH or (candidate is not None and len(candidate) > MAX_TEXT_LENGTH):
        raise ValueError("text exceeds editorial review limit")
    supplied = candidate is not None
    proposed = text if candidate is None else candidate
    protected = _protected_ranges(text)
    suggestions = []
    for phrase, replacement, message in _PHRASES:
        for match in re.finditer(re.escape(phrase), text):
            if any(match.start() < end and match.end() > start for start, end in protected):
                continue
            suggestions.append({"code": "phrase_clarity", "span": _span(match.start(), match.end(), text),
                                "replacement": replacement, "message": message,
                                "safe_to_apply": False, "requires_human_review": True})
    diagnostics = _structure(text, profile)
    if not text.strip():
        diagnostics.append({"code": "empty_text", "severity": "warning", "message": "没有可审查正文。"})
    for start, end, sentence in _sentences(text):
        if len(sentence.strip()) > (100 if profile == "conversation_summary" else 160):
            diagnostics.append({"code": "long_sentence", "severity": "suggestion", "span": _span(start, end, text),
                                "message": "考虑按论点拆句，保留条件、否定、数据和因果关系。"})
    for paragraph in re.finditer(r"[^\n]+", text):
        if len(paragraph.group().strip()) > 400:
            diagnostics.append({"code": "dense_paragraph", "severity": "suggestion",
                                "span": _span(paragraph.start(), paragraph.end(), text),
                                "message": "段落较密集，考虑按背景、证据、结论或操作步骤分段；不要拆散条件关系。"})
    # Surface-form variants are clues, not an assertion that terms are synonyms.
    for variants in (("数据集", "资料集"), ("用户ID", "用户Id", "用户id"), ("API", "Api", "api"), ("毫升", "mL", "ml")):
        present = [term for term in variants if term in text]
        if len(present) > 1:
            diagnostics.append({"code": "terminology_consistency", "severity": "suggestion",
                                "terms": present, "requires_human_review": True,
                                "message": "发现可能的术语或记法变体；确认指代相同后统一，代码标识、引文和单位大小写不得盲改。"})
    seen = set()
    for start, end, sentence in _sentences(text):
        key = sentence.strip()
        if len(key) >= 12 and key in seen:
            diagnostics.append({"code": "repeated_sentence", "severity": "suggestion", "span": _span(start, end, text),
                                "message": "此句重复；确认不是必要重申、引用或不同上下文后再精简。"})
        seen.add(key)
    changed = text != proposed
    mechanical = changed and proposed == text.replace("\r\n", "\n")
    risks = []
    inventories = {}
    for name, pattern in {"numbers": _NUMBERS, "quantities": _QUANTITIES, "citations": _CITATIONS, "formulas": _FORMULAS, **_MARKERS}.items():
        old = [m.group() for m in pattern.finditer(text)]
        new = [m.group() for m in pattern.finditer(proposed)]
        inventories[name] = {"original": old, "candidate": new, "sequence_unchanged": old == new}
        if old != new:
            risks.append({"code": name + "_changed", "severity": "warning",
                          "removed": list((Counter(old) - Counter(new)).elements()),
                          "added": list((Counter(new) - Counter(old)).elements()),
                          "message": "受保护内容或顺序变化，需要人工核对原文和候选文本。"})
    # Whole changed sentences flag context reassignment even when token lists match.
    contextual = []
    if changed and not mechanical:
        for start, end, sentence in _sentences(text):
            categories = [name for name, pattern in {"numbers": _NUMBERS, "quantities": _QUANTITIES, "citations": _CITATIONS, "formulas": _FORMULAS, **_MARKERS}.items() if pattern.search(sentence)]
            if categories and sentence not in proposed:
                contextual.append({"span": _span(start, end, text), "categories": categories})
        risks.append({"code": "substantive_rewrite", "severity": "warning",
                      "message": "任何实质改写均需复核；词项一致不能证明事实、语义或结论保持不变。"})
    return {
        "schema_version": 1, "profile": profile, "review_mode": "deterministic_rules_only",
        "status": "review_required" if risks or suggestions or diagnostics else "no_rule_findings",
        "original": text, "candidate": proposed, "candidate_supplied": supplied,
        "changed": changed, "changed_spans": _changes(text, proposed) if changed else [],
        "offset_unit": "unicode_code_point", "end_offsets": "exclusive",
        "suggestions": suggestions, "structure_diagnostics": diagnostics,
        "rewrite_risks": risks, "protected_content": inventories,
        "changed_protected_sentences": contextual,
        "permitted_edits": [{"operation": "normalize_crlf_to_lf", "scope": "line_endings_only"}],
        "candidate_within_permitted_edits": not changed or mechanical,
        "applied": False, "semantic_review": "not_run", "factual_verification": "not_run",
        "capability_limits": [
            "规则和关键词只提供审查线索，可能漏检或误报。",
            "没有调用语义模型；不验证真实性、引用有效性、因果关系或结论等价。",
            "数字与引用逐项比较不能证明其对应对象和上下文未变。",
            "必要科学限制、否定和结论不能为追求简洁而自动删除。",
            "不会修改文档；候选文本和建议必须由用户或获授权审查者确认。",
        ],
    }
