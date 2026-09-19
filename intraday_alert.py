# -*- coding: utf-8 -*-
"""盘中卖点提醒:每5分钟检查推送记录(最近3个交易日)中 S/A 级标的的实时行情,
按规则触发提醒并发送到飞书群。由 GitHub Actions 驱动,状态持久化到仓库。
"""
import datetime
import glob
import json
import os
import sys
import urllib.request
import zoneinfo

TZ = zoneinfo.ZoneInfo("Asia/Shanghai")
NOW = datetime.datetime.now(TZ)

# ---------- 交易时段判断 ----------
def in_trading_hours(now: datetime.datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.strftime("%H:%M")
    return ("09:30" <= t <= "11:30") or ("13:00" <= t <= "15:00")


# ---------- 行情 ----------
def fetch_quotes(codes: list) -> dict:
    """腾讯行情,返回 {code: {price, prevClose, open, high, low, limitUp, avg, vol}}"""
    syms = ",".join(codes)
    url = f"https://qt.gtimg.cn/q={syms}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=15).read().decode("gbk", errors="replace")
    out = {}
    for line in raw.strip().splitlines():
        if "=" not in line or '="' not in line:
            continue
        payload = line.split('="', 1)[1].rstrip('";')
        f = payload.split("~")
        if len(f) < 49:
            continue
        code = f[2]
        try:
            price = float(f[3]); prev = float(f[4]); open_p = float(f[5]); high = float(f[33]); low = float(f[34])
            limit_up = float(f[47])
            vol_hand = float(f[35].split("/")[1]); amount = float(f[35].split("/")[2])
            avg = amount / (vol_hand * 100) if vol_hand else price
            out[code] = {"price": price, "prevClose": prev, "open": open_p, "high": high, "low": low,
                         "limitUp": limit_up, "avg": avg, "time": f[30]}
        except (ValueError, IndexError):
            continue
    return out


# ---------- 记录与状态 ----------
def load_records() -> list:
    """取最近3个交易日的推送记录,合并股票列表,每只附带 refPrice 与推送日期"""
    files = sorted(glob.glob("push_history/*.json"))[-3:]
    stocks = []
    for fp in files:
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("stocks", []):
            s["_date"] = d.get("date", fp[-12:-5])
            stocks.append(s)
    return stocks


def load_state() -> dict:
    try:
        return json.load(open("alerts_state.json", encoding="utf-8"))
    except Exception:
        return {}


# ---------- 规则 ----------
def evaluate(stock: dict, q: dict, now: datetime.datetime) -> list:
    """返回触发提醒的规则名列表"""
    alerts = []
    ref = float(stock["refPrice"])
    price, high, prev, limit_up, avg = q["price"], q["high"], q["prevClose"], q["limitUp"], q["avg"]
    open_p = q.get("open", price)
    hhmm = now.strftime("%H:%M")
    grade = stock.get("grade", "")

    # 弱转强确认买点(仅 W 级观察票,14:30前,当日只报一次)
    if stock.get("watchBuy") and grade == "W" and hhmm < "14:30":
        if price >= ref * 1.02 and price >= avg and price >= open_p:
            alerts.append(f"弱转强确认买点:现价{price:.2f}站上参考价+2%、分时均价与开盘价,量价配合可介入(轻仓)")
        elif price >= ref * 1.03 and price >= avg:
            alerts.append(f"弱转强强势确认:现价{price:.2f}超参考价3%且站上均价,注意追高风险")

    # R 级(龙虎榜无溢价风险票):只提示风险不提示买点
    if grade == "R":
        if price <= ref * 0.98:
            alerts.append(f"风险票走弱:现价{price:.2f}跌破参考价{ref:.2f}2%,按昨日龙虎榜风险提示执行回避")
        if hhmm >= "14:45" and price < ref:
            alerts.append(f"风险票尾盘弱势:现价{price:.2f}低于参考价,收盘前回避")
        return alerts

    # S/A 级卖点规则
    # 1. 止损: 跌破参考价3%
    if price <= ref * 0.97:
        alerts.append(f"止损警报:现价{price:.2f}跌破参考价{ref:.2f}超3%")
    # 2. 炸板: 摸过涨停但没封住(回落到昨收+5%以内)
    if high >= limit_up * 0.995 and price <= prev * 1.05:
        alerts.append(f"炸板警报:盘中摸板{high:.2f}后回落至{price:.2f}")
    # 3. 冲高回落止盈: 冲过+5%后跌回+2%以内
    if high >= ref * 1.05 and price <= ref * 1.02:
        alerts.append(f"冲高回落止盈:最高{high:.2f}(+{(high/ref-1)*100:.1f}%)现回落至{price:.2f}")
    # 4. 尾盘弱势: 14:45后仍绿盘且在均价下方
    if hhmm >= "14:45" and price < ref and price < avg:
        alerts.append(f"尾盘弱势:现价{price:.2f}低于参考价与均价{avg:.2f},收盘前考虑减仓")
    # 5. 涨停封板: 持有提示
    if price >= limit_up * 0.995:
        alerts.append(f"涨停封板:现价{price:.2f}封板,可继续持有")
    return alerts


# ---------- 发送 ----------
def send_feishu(text: str) -> bool:
    webhook = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook:
        return False
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")).get("StatusCode") == 0
    except Exception:
        return False


def main() -> None:
    force = "--force" in sys.argv
    if not in_trading_hours(NOW) and not force:
        print("off hours, skip")
        return

    records = load_records()
    if not records:
        print("no records, skip")
        return

    stocks = [(s, (f"sh{s['code']}" if s["code"].startswith(("5", "6", "9")) else f"sz{s['code']}")) for s in records]
    quotes = fetch_quotes([sym for _, sym in stocks])

    state = load_state()
    today = NOW.strftime("%Y%m%d")
    fired = []
    for stock, sym in stocks:
        q = quotes.get(stock["code"])
        if not q:
            continue
        alerts = evaluate(stock, q, NOW)
        for a in alerts:
            key = f"{today}:{stock['code']}:{a[:4]}"  # 每只票每种规则每天只报一次
            if key in state:
                continue
            state[key] = now_str()
            fired.append(f"[{stock['grade']}级]{stock['name']}({stock['code']}) 参考价{stock['refPrice']}\n{a}")

    if fired:
        text = "【竞价扫描盘中提醒】" + NOW.strftime("%m-%d %H:%M") + "\n" + "\n\n".join(fired)
        ok = send_feishu(text)
        print("feishu:", ok, "\n", text)
        json.dump(state, open("alerts_state.json", "w", encoding="utf-8"), ensure_ascii=False)
    else:
        print("no new alerts")


def now_str():
    return NOW.strftime("%Y%m%d%H%M")


if __name__ == "__main__":
    main()
