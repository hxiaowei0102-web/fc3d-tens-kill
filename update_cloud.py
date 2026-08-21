# -*- coding: utf-8 -*-
"""
福彩3D 十位杀一码 — 云端一键更新（GitHub Actions 入口）
=============================================
流程：多源抓取最新开奖追加CSV → 指纹判断：
  ① 数据未变：跳过穷举/回测（复用缓存与页面），仍保留页面文件供 Pages 部署
  ② 数据已变：暴力穷举5924万×500期 → 网格扫描 → 500/1000期回测+下期预测 → 生成页面
缓存：cache/pool.json、cache/result.json 按 fingerprint 复用。
所有产物（data/csv、cache、index.html）由 workflow 统一 git commit 提交，实现云端自动更新。
"""
import io
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BJT = timezone(timedelta(hours=8))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_HTML = os.path.join(BASE_DIR, 'index.html')


def current_fingerprint():
    from engine import load_data
    issues, _, _, _ = load_data()
    return f"{len(issues)}_{issues[-1]}"


def main():
    t0 = time.time()
    print("=" * 46)
    print("  福彩3D 十位杀一码 · 云端全自动更新")
    print(f"  时间(北京): {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 46)

    fp = current_fingerprint()
    print(f"  数据指纹: {fp}")

    # ---- [1/5] 数据同步（云端多源降级）----
    print("\n[1/5] 同步最新数据（云端多源降级 + CSV兜底）")
    try:
        import fetch
        fetch.sync_data()
    except Exception as e:
        print(f"  ⚠ 数据同步异常，沿用现有CSV: {str(e)[:80]}")
    fp2 = current_fingerprint()
    changed = (fp2 != fp)
    if changed:
        fp = fp2
        print(f"  ✅ 数据已更新 → 指纹 {fp}")
    else:
        print(f"  ➖ 数据无变化（已是最新），跳过重算")

    from formulas import FEAT_VERSION, NF

    # ---- [2/5] 暴力穷举 ----
    # 触发条件：① 数据变化 ② 缓存缺失（首次部署/缓存丢失）——两种情况都需重算
    need_pool = True
    if os.path.exists('cache/pool.json'):
        with open('cache/pool.json', 'r', encoding='utf-8') as f:
            pj = json.load(f)
        pfp = f"{pj['data_info']['n_issues']}_{pj['data_info']['last']}"
        if pfp == fp and pj.get('feat_version') == FEAT_VERSION:
            need_pool = False
    if need_pool:
        print("\n[2/5] 暴力穷举（最新500期，5924万公式，按族限选 Top560 专家池）" if changed
              else "\n[2/5] 暴力穷举（缓存缺失，强制重算）")
        import bruteforce500
        bruteforce500.main()
    else:
        print("  [2/5] 穷举缓存命中，跳过")

    # ---- [3/5][4/5] 网格扫描 + 回测 + 下期预测 ----
    need_result = True
    if os.path.exists('cache/result.json'):
        with open('cache/result.json', 'r', encoding='utf-8') as f:
            rj = json.load(f)
        if rj.get('fingerprint') == fp and rj.get('pool_info', {}).get('feat_version') == FEAT_VERSION:
            need_result = False
    if need_result:
        import hedge_core as _hc
        print(f"\n[3/5] 网格扫描（{len(_hc.WIN_GRID) * len(_hc.K_GRID)}组合 win×K 自动选优）" if changed
              else "\n[3/5] 网格扫描（缓存缺失，强制重算）")
        print("[4/5] 500期 Hedge 逐期真实回测 + 1000期连续回测 + 下期预测")
        import hedge_core
        hedge_core.main()
    else:
        print("  [3/5][4/5] 回测缓存命中，跳过")

    # 数据是否发生了变化（影响提交决策与提示语）
    data_changed = changed or need_pool or need_result

    # ---- [5/5] 生成网页（每次运行都生成，保证 Pages 始终有最新页面）----
    print("\n[5/5] 生成静态网页 index.html")
    import gen_site
    gen_site.main()

    # 报告变更状态（workflow 据此决定是否提交）
    print(f"\n{'✅ 数据已更新，页面已重算' if data_changed else '➖ 数据未变，页面复用缓存'}")
    print(f"  总耗时 {time.time()-t0:.1f} 秒")
    print(f"  产物: index.html / data/fc3d-history.csv / cache/pool.json / cache/result.json")


if __name__ == '__main__':
    main()
