"""Local evidence-bound summaries. No model, imported claims, or semantic approval."""
from __future__ import annotations
import hashlib
import json

LABELS = {'code':'代码语法', 'text':'文字规则', 'model':'模型审查', 'browser':'浏览器验证', 'native':'实机验证'}
STATES = {'pass':'通过', 'fail':'失败', 'blocked':'阻塞', 'not_run':'未运行', 'not_required':'未要求（未据此验证）'}
LIMITS = {
 'code':'仅 Python AST / JSON 语法，不含运行、测试或安全审查。',
 'text':'仅本地规则诊断，建议未应用；未核验事实或语义。',
 'model':'未配置模型，未进行模型审查。',
 'browser':'未配置浏览器适配器，未进行浏览器验证。',
 'native':'未配置实机适配器，未进行实机验证。',
}

def receipt_digest(receipt: dict) -> str:
    payload = {k:v for k,v in receipt.items() if k != 'receipt_sha256'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()).hexdigest()

def build_report(plan: dict, gate: dict, generated_at: str) -> dict:
    """Called under Engine lock after re-evaluating the current source gate.

    Source unavailable and stale source both invalidate previous passes. Evidence
    statuses are retained separately as historical observations, never upgraded.
    The digest detects accidental changes; it is not a signature/authentication.
    """
    invalid = gate.get('stale', False) or 'checks' not in gate
    checks = []
    for check, label in LABELS.items():
        required = check in plan['required']
        evidence = plan['evidence'].get(check)
        observed = evidence.get('status', 'not_run') if evidence else 'not_run'
        status = ('blocked' if invalid else observed) if required else 'not_required'
        checks.append({'check':check, 'label':label, 'required':required,
                       'status':status, 'observed_status':observed,
                       'evidence_id':evidence['id'] if evidence else None,
                       'finished_at':evidence.get('finished_at') if evidence else None,
                       'limit':LIMITS[check]})
    receipt = {'schema_version':1, 'plan_id':plan['id'], 'generated_at':generated_at,
               'decision_id':gate.get('decision_id'), 'allow_completion':gate.get('allow_completion') is True,
               'source_valid':not invalid, 'scope_mode':plan['scope'],
               'planned_artifact_hashes':dict(plan['snapshot']),
               'repository_binding': ({
                   'manifest_sha256': hashlib.sha256(json.dumps(plan['manifest'], sort_keys=True).encode()).hexdigest(),
                   'file_count':len(plan['manifest']['files']),
                   'excluded_directory_names':list(plan['manifest']['excluded_directory_names']),
                   'limit':'仅绑定文件内容；不含 Git HEAD、权限及空目录，未检查所有文件正确性。'
               } if plan['manifest'] is not None else None),
               'checks':checks, 'method':'deterministic_evidence_summary',
               'llm_pass':False, 'applied':False,
               'scope':'仅本计划要求的检查；不代表整个项目完成或生产可用。',
               'integrity_limit':'SHA-256 为内容校验，非数字签名；收尾时仍须重新调用 gate。'}
    lines = ['本计划检查已满足。' if receipt['allow_completion'] else '本计划尚不能收尾。']
    if invalid:
        lines.append('文件已变更或不可读取，旧结果不能用于当前收尾；需重新制定计划并检查。')
    lines.extend(f"- {c['label']}：{STATES[c['status']]}。" for c in checks)
    # Always retain the exact configured capability limits, including checks
    # not requested. No stdout, external source prose, or model prose is echoed.
    lines.append('范围：' + receipt['scope'])
    lines.append('仅检查列出的文件；仓库 manifest 只绑定其余文件内容，不验证其正确性。' if plan['scope'] == 'repository' else '仅检查列出的文件，不覆盖仓库其他文件。')
    lines.extend(c['limit'] for c in checks if c['required'])
    receipt['summary'] = '\n'.join(lines)
    receipt['receipt_sha256'] = receipt_digest(receipt)
    return receipt
