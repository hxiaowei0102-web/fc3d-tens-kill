# -*- coding: utf-8 -*-
"""
福彩3D 十位杀一码 — 一键更新（本地/云端单入口）
=============================================
流程：联网补抓最新开奖(多源降级+跨源校验+CSV兜底) → 暴力穷举5924万×500期选专家池
      → 网格扫描选Hedge参数 → 500期逐期真实回测+下期预测 → 生成静态网页
缓存：cache/pool.json、cache/result.json 按 fingerprint 复用（--force 强制重算）。
用法：
  python update.py          本地模式 → 输出 十位杀一码.html
  python update.py --cloud  云端模式 → 输出 index.html（GitHub Pages 入口）
  python update.py --force  强制重算（忽略缓存）
fingerprint 三要素统一：期数_最新期号_特征版本（与 hedge_core 写入 result.json 的格式完全一致），
保证数据未变时缓存命中，避免云端每次 cron 重复重算。
"""
import argparse
import io
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BJT = timezone(timedelta(hours=8))


def current_fingerprint():
    """与 hedge_core.py 写入 result.json 的 fingerprint 格式完全一致：期数_最新期号_特征版本"""
    from engine import load_data
    from formulas import FEAT_VERSION
    issues, _, _, _ = load_data()
    return f"{len(issues)}_{issues[-1]}_{FEAT_VERSION}"


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser(description='福彩3D 十位杀一码 一键更新')
    ap.add_argument('--cloud', action='store_true', help='云端模式：输出 index.html（GitHub Pages 入口）')
    ap.add_argument('--force', action='store_true', help='强制重算（忽略缓存）')
    args = ap.parse_args()

    mode = '云端' if args.cloud else '本地'
    print("=" * 46)
    print(f"  福彩3D 十位杀一码 · 一键更新（{mode}）")
    print(f"  时间(北京): {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 46)

    # 云端模式：设置输出文件为 index.html
    if args.cloud:
        os.environ['FC3D_OUT_HTML'] = 'index.html'

    fp = current_fingerprint()
    print(f"  数据指纹: {fp}")

    # ---- [1/5] 数据同步 ----
    print("\n[1/5] 同步最新数据（多源降级 + 跨源校验 + CSV兜底）")
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
        print("  ➖ 数据无变化（已是最新），跳过重算")

    # ---- [1.5/5] 真实预测归档：回填已开奖期的结果 ----
    try:
        import archive
        archive.backfill_results()
    except Exception as e:
        print(f"  ⚠ 回填真实预测结果异常: {str(e)[:80]}")

    # ---- [2/5] 暴力穷举（5924万×500期 → 专家池）----
    from formulas import FEAT_VERSION
    from engine import load_data
    need_pool = True
    if os.path.exists('cache/pool.json') and not args.force:
        with open('cache/pool.json', 'r', encoding='utf-8') as f:
            pj = json.load(f)
        issues, _, _, _ = load_data()
        exp_pool = f"{len(issues)}_{issues[-1]}"  # pool.json 只存两要素 + 顶层 feat_version
        pfp = f"{pj['data_info']['n_issues']}_{pj['data_info']['last']}"
        if pfp == exp_pool and pj.get('feat_version') == FEAT_VERSION:
            print(f"  [2/5] 穷举缓存命中（指纹 {fp}），跳过")
            need_pool = False
    if need_pool:
        print("\n[2/5] 暴力穷举（最新500期，5924万公式，按族限选 Top560 专家池）")
        import bruteforce500
        bruteforce500.main()
    else:
        print("  [2/5] 穷举缓存命中，跳过")

    # ---- [3/5][4/5] 网格扫描 + 500期回测 + 下期预测 ----
    need_result = True
    if os.path.exists('cache/result.json') and not args.force:
        with open('cache/result.json', 'r', encoding='utf-8') as f:
            rj = json.load(f)
        if rj.get('fingerprint') == fp:
            print(f"  [3/5][4/5] 回测缓存命中（指纹 {fp}），跳过重算")
            need_result = False
    if need_result:
        import hedge_core as _hc
        print(f"\n[3/5] 网格扫描（{len(_hc.WIN_GRID) * len(_hc.K_GRID)}组合 win×K 自动选优）")
        print("[4/5] 500期 Hedge 逐期真实回测 + 1000期连续回测 + 下期预测")
        import hedge_core
        hedge_core.main()
    else:
        print("  [3/5][4/5] 回测缓存命中，跳过")

    data_changed = changed or need_pool or need_result

    # ---- [5/5] 真实预测归档（每次运行都归档当期真实预测，幂等去重）----
    try:
        import archive
        import json as _json
        with open('cache/result.json', 'r', encoding='utf-8') as _f:
            _result = _json.load(_f)
        archive.archive_prediction(_result)
    except Exception as e:
        print(f"  ⚠ 归档真实预测异常: {str(e)[:80]}")

    # ---- [6/5] 生成网页 ----
    print("\n[5/5] 生成静态网页")
    import gen_site
    gen_site.main()

    print(f"\n{'✅ 数据已更新，页面已重算' if data_changed else '➖ 数据未变，页面复用缓存'}")
    print(f"  总耗时 {time.time()-t0:.1f} 秒")
    if not args.cloud:
        print("本地预览: http://127.0.0.1:8899/十位杀一码.html  (双击 HTML 文件亦可)")


if __name__ == '__main__':
    main()
