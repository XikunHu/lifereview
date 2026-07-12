#!/usr/bin/env python3
"""import-hae.py — 把 HAE (Health Auto Export) JSON 导入 SQLite health.db

根治 iCloud evict 问题的核心脚本：
- DB 文件在本地 (~/.life-log/db/health.db)，永不被 iCloud 回收
- morning-brief.py 只查 DB，不再 open iCloud 文件 → 永不 hang
- 本脚本才碰 HAE 文件，_warm_read 带 daemon 线程硬超时，hang 了跳过该文件（不卡死）

用法:
  python3 import-hae.py              # 导入昨天 + 今天
  python3 import-hae.py 2026-07-11   # 导入指定日期
  python3 import-hae.py --all        # 全量回填（HAE_BASE 所有文件）
"""
import json, os, sys, statistics, sqlite3, time, subprocess, threading
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.life-log/db/health.db")
HAE_BASES = [
    os.path.expanduser("~/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/iCloud for HealthExport"),
    os.path.expanduser("~/Library/Mobile Documents/iCloud~com~ifunography~HealthExport/Documents/secondary-export"),
]


def _warm_read(fn, retries=3, hard_timeout=15):
    """安全读 HAE 文件，绝不卡死：
    daemon 线程跑 open+json.load，join(hard_timeout) 硬超时兜底
    → 即使 open() 陷入 iCloud 内核 deadlock，主线程也能脱身
    OSError → brctl download 预热后重试；JSONDecodeError → 返回 None。"""
    def _load(box):
        try:
            with open(fn) as fp:
                box[0] = json.load(fp)
        except BaseException as e:
            box[1] = e
    for i in range(retries):
        box = [None, None]
        t = threading.Thread(target=_load, args=(box,), daemon=True)
        t.start()
        t.join(timeout=hard_timeout)
        if t.is_alive():
            print(f"[WARN] open() 超时 {hard_timeout}s（iCloud deadlock），跳过 {os.path.basename(fn)}", file=sys.stderr)
            return None
        if box[1] is None:
            return box[0]
        err = box[1]
        if isinstance(err, json.JSONDecodeError):
            print(f"[WARN] JSON 解析失败 {os.path.basename(fn)}: {err}", file=sys.stderr)
            return None
        if isinstance(err, OSError):
            try:
                subprocess.run(['brctl', 'download', fn], stderr=subprocess.DEVNULL, timeout=10)
            except subprocess.TimeoutExpired:
                print(f"[WARN] brctl download 超时，跳过 {os.path.basename(fn)}", file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))
            continue
        print(f"[WARN] {os.path.basename(fn)} 读取异常: {type(err).__name__}: {err}", file=sys.stderr)
        return None
    return None


def parse_hae(date, data):
    """从 HAE JSON 提取每日关键指标。逻辑与 morning-brief.py get_hae 一致。
    返回 (metrics_list, sleep_tuple_or_None)"""
    mm = {m['name']: m for m in data['data']['metrics']}
    metrics = []
    # RHR
    if 'resting_heart_rate' in mm:
        vals = [p['qty'] for p in mm['resting_heart_rate']['data'] if p.get('qty')]
        if vals:
            metrics.append(('rhr', statistics.median(vals), 'bpm'))
    # HRV 夜间中位数（剔除异常值）
    if 'heart_rate_variability' in mm:
        pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm['heart_rate_variability']['data'] if p.get('qty')]
        night = [v for h, v in pts if 0 <= h < 9]
        pool = night if night else [v for _, v in pts]
        if pool:
            m_med = statistics.median(pool)
            clean = [v for v in pool if v <= m_med * 2] or pool
            metrics.append(('hrv', statistics.median(clean), 'ms'))
            metrics.append(('hrv_n', len(night), 'count'))
    # 夜间呼吸
    if 'respiratory_rate' in mm:
        pts = [(int(p['date'].split()[1][:2]), p['qty']) for p in mm['respiratory_rate']['data'] if p.get('qty')]
        night = [v for h, v in pts if 0 <= h < 9]
        if night:
            metrics.append(('resp', statistics.median(night), '/min'))
    # 步数 / 活动能量
    if 'step_count' in mm:
        metrics.append(('steps', sum(p.get('qty', 0) or 0 for p in mm['step_count']['data']), 'count'))
    if 'active_energy' in mm:
        metrics.append(('active', sum(p.get('qty', 0) or 0 for p in mm['active_energy']['data']), 'kcal'))
    # 睡眠（醒来日归属）
    sleep = None
    if 'sleep_analysis' in mm:
        for p in mm['sleep_analysis']['data']:
            ts = float(p.get('totalSleep', 0))
            if ts > 0:
                sleep = (date, p.get('sleepStart', '')[:16], p.get('sleepEnd', '')[:16],
                         ts, float(p.get('deep', 0)), float(p.get('rem', 0)))
                break
    return metrics, sleep


def import_one(con, date):
    fn = None
    for base in HAE_BASES:
        p = os.path.join(base, f"HealthAutoExport-{date}.json")
        if os.path.exists(p):
            fn = p
            break
    if fn is None:
        return False, "文件不存在"
    data = _warm_read(fn)
    if data is None:
        return False, "读取失败（iCloud evict/deadlock，已跳过）"
    metrics, sleep = parse_hae(date, data)
    cur = con.cursor()
    for name, value, unit in metrics:
        cur.execute("""
            INSERT INTO metrics (date, metric_name, value, unit, source)
            VALUES (?, ?, ?, ?, 'HAE')
            ON CONFLICT(date, metric_name, source) DO UPDATE SET
                value=excluded.value, imported_at=datetime('now','localtime')
        """, (date, name, value, unit))
    if sleep:
        cur.execute("""
            INSERT INTO sleep_sessions (sleep_date, start_time, end_time, total_hours, deep_hours, rem_hours, source)
            VALUES (?, ?, ?, ?, ?, ?, 'HAE')
            ON CONFLICT(sleep_date) DO UPDATE SET
                start_time=excluded.start_time, end_time=excluded.end_time,
                total_hours=excluded.total_hours, deep_hours=excluded.deep_hours,
                rem_hours=excluded.rem_hours
        """, sleep)
    con.commit()
    return True, f"{len(metrics)} 指标" + (" + 睡眠" if sleep else "")


def main():
    if '--all' in sys.argv:
        dates = sorted(set(
            f.replace('HealthAutoExport-', '').replace('.json', '')
            for base in HAE_BASES
            for f in os.listdir(base)
            if f.startswith('HealthAutoExport-') and f.endswith('.json')
        ))
        print(f"全量回填: {len(dates)} 天 (跨 {len(HAE_BASES)} 目录)")
    elif len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        dates = [sys.argv[1]]
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        yday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        dates = [yday, today]

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    ok = fail = 0
    for d in dates:
        success, msg = import_one(con, d)
        if success:
            print(f"✅ {d}: {msg}")
            ok += 1
        else:
            print(f"❌ {d}: {msg}")
            fail += 1
    con.close()
    # Dead Man's Switch：成功导入则写心跳时间戳（晨报据此告警管道中断）
    if ok > 0:
        with open(os.path.expanduser('~/.life-log/db/last-ingestion.txt'), 'w') as _f:
            _f.write(f"{datetime.now().isoformat()}\n{DB_PATH}\n{ok} days ok")
        # ② 备份钩子：cp 一份到 backups/，滚动保留 14 天
        import shutil, glob
        backup_dir = os.path.join(os.path.dirname(DB_PATH), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d')
        shutil.copy2(DB_PATH, os.path.join(backup_dir, f'health-{stamp}.db'))
        cutoff = datetime.now() - timedelta(days=14)
        for old in glob.glob(os.path.join(backup_dir, 'health-*.db')):
            try:
                d = datetime.strptime(os.path.basename(old)[7:15], '%Y%m%d')
                if d < cutoff:
                    os.remove(old)
            except ValueError:
                continue
        print(f"[OK] 已备份 → backups/health-{stamp}.db（滚动保留 14 天）")
        # ③ git dump：DB 导成文本 SQL 提交到 ~/.life-log/ git 仓库
        try:
            dump_path = os.path.join(os.path.dirname(DB_PATH), 'health-dump.sql')
            with open(dump_path, 'w') as _df:
                subprocess.run(['sqlite3', DB_PATH, '.dump'], stdout=_df, timeout=30)
            _ll = os.path.expanduser('~/.life-log')
            subprocess.run(['git', '-C', _ll, 'add', '-A'], timeout=30, capture_output=True)
            _r = subprocess.run(['git', '-C', _ll, 'commit', '-m', f'health data {stamp}'],
                                timeout=30, capture_output=True, text=True)
            if _r.returncode == 0:
                print(f"[OK] git 已提交 health-dump.sql（{stamp}）")
                # 自动 push 到私有仓库 life-review-log（异地容灾）
                _p = subprocess.run(['git', '-C', _ll, 'push', 'origin', 'main'],
                                    timeout=60, capture_output=True, text=True)
                if _p.returncode == 0:
                    print(f"[OK] 已 push → life-review-log（异地容灾）")
                else:
                    print(f"[WARN] push 失败: {_p.stderr[:120]}", file=sys.stderr)
        except Exception as _e:
            print(f"[WARN] git dump 跳过: {type(_e).__name__}", file=sys.stderr)
    print(f"\n完成: {ok} 成功, {fail} 失败. DB: {DB_PATH}")


if __name__ == '__main__':
    main()
