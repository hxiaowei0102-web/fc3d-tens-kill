# -*- coding: utf-8 -*-
"""
福彩3D 十位杀一码 — 真实预测归档（逐期真实预测记录）
================================================
背景：回测表是"事后用最终参数统一重算"的（walk-forward 但参数是事后定的），
     不是每一期当时真实发布的杀码。老板要的"逐期真实预测记录"= 每一期开奖前
     系统当时真正确认发布的预测（含当时的 win/k 参数与发布时间）。

本模块从今天起逐期归档：
  1. 每次生成 result.json 后，把 next（预测期/杀码/参数/发布时间）追加到
     data/real_predictions.jsonl（按 预测期号 去重，重复运行不产生垃圾）
  2. 下次数据更新时，若某预测期已在 CSV 中出现（已开奖），
     回填开奖结果（num/tens/hit）→ 形成"预测→结果"闭环
  3. 页面展示：逐期真实预测记录（预测期/杀码/参数/发布时间/开奖结果/命中）

文件：data/real_predictions.jsonl（追加型日志，云端随 git 提交，天然多机同步）
"""
import json
import os

REAL_LOG = os.path.join('data', 'real_predictions.jsonl')


def _load_log():
    """读取全部真实预测记录，按预测期号索引"""
    recs = {}
    if os.path.exists(REAL_LOG):
        with open(REAL_LOG, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    recs[r['target_issue']] = r
                except (ValueError, KeyError):
                    continue
    return recs


def archive_prediction(result):
    """
    从 result.json 归档当期真实预测。
    幂等：同一预测期号已存在则不重复追加（保留最早发布版本）。
    """
    n = result.get('next', {})
    target = str(n.get('target_issue', ''))
    if not target:
        return False
    recs = _load_log()
    if target in recs:
        return False                      # 已归档，不覆盖（保留首次发布）
    rec = {
        'target_issue': target,           # 预测期号
        'kill': int(n['kill']),           # 真实发布的杀码
        'win': int(result['params']['win']),   # 当时的最优参数
        'k': int(result['params']['k']),
        'published_at': result.get('generated_at', ''),   # 发布时间（北京）
        'last_issue': str(n.get('last_issue', '')),       # 预测时的数据截至期
        'last_draw': str(n.get('last_draw', '')),
        'top3': [int(x) for x in n.get('top3_vote', [n['kill']])[:3]],
    }
    os.makedirs('data', exist_ok=True)
    with open(REAL_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f"  📝 真实预测归档: {target} 杀{rec['kill']} (win={rec['win']}/k={rec['k']}, {rec['published_at']})")
    return True


def backfill_results():
    """
    回填已开奖期的结果：用 CSV 里的开奖号补 num/tens/hit。
    返回回填条数（页面提示用）。
    """
    from engine import load_data
    issues, hh, tt, oo = load_data()
    draw = {str(iss): (h, t, o) for iss, h, t, o in zip(issues, hh, tt, oo)}
    recs = _load_log()
    filled = 0
    changed = False
    for target, rec in sorted(recs.items()):
        if 'num' in rec:
            continue                      # 已回填
        if target in draw:
            h, t, o = draw[target]
            rec['num'] = f"{h}{t}{o}"
            rec['tens'] = int(t)
            rec['hit'] = bool(rec['kill'] != int(t))
            changed = True
            filled += 1
            print(f"  ✅ 回填结果: {target} 开奖{rec['num']} 十位{rec['tens']} "
                  f"杀{rec['kill']} {'✅命中' if rec['hit'] else '❌杀错'}")
    if changed:
        os.makedirs('data', exist_ok=True)
        with open(REAL_LOG, 'w', encoding='utf-8') as f:
            for target in sorted(recs.keys()):
                f.write(json.dumps(recs[target], ensure_ascii=False) + '\n')
    return filled


def load_records():
    """页面用：返回按预测期倒序（近期在上）的完整记录列表"""
    recs = _load_log()
    out = list(recs.values())
    out.sort(key=lambda r: r['target_issue'], reverse=True)
    return out
