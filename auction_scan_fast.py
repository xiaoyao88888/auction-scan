# -*- coding: utf-8 -*-
"""9:27 秒级竞价推送:直连悟道 MCP 拉数据,按 v4-v8 确定性规则出 S/A/B,飞书+邮箱+marker。
用法: python auction_scan_fast.py [--dry-run]
"""
import base64
import datetime
import json
import os
import smtplib
import sys
import time
import urllib.request
import zoneinfo
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

API = "https://stock.quicktiny.cn/api/mcp-stream"
def _local_secret(fname):
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        return open(p, encoding="utf-8").read().strip()
    except Exception:
        return ""

AUTH = "Bearer " + (os.environ.get("WUDAO_TOKEN") or _local_secret("wudao_token.txt"))
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK") or _local_secret("feishu_webhook.txt")
SMTP_HOST, SMTP_PORT = "smtp.qq.com", 465
MAIL_ADDR = "215477645@qq.com"
GH_API = "https://api.github.com/repos/xiaoyao88888/auction-scan"
DRY = "--dry-run" in sys.argv
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def rpc(name, args, rid=1):
    payload = {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
               "params": {"name": name, "arguments": args}}
    req = urllib.request.Request(API, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Authorization": AUTH, "Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    if body.lstrip().startswith("data:"):  # SSE 兜底
        body = "\n".join(l.split("data:", 1)[1] for l in body.splitlines() if l.startswith("data:"))
    return json.loads(body)


def call_tool(name, args):
    out = rpc(name, args)
    sc = out.get("result", {}).get("structuredContent", {})
    if isinstance(sc, dict) and "data" in sc:
        return sc["data"]
    txt = out.get("result", {}).get("content", [{}])[0].get("text", "")
    try:
        return json.loads(txt)
    except Exception:
        return txt


def pull_with_retry(name, args, tries=3):
    for i in range(tries):
        try:
            d = call_tool(name, args)
            rows = d.get("rows") if isinstance(d, dict) else None
            if rows is None or len(rows) > 0:
                return d
            time.sleep(20)
        except Exception:
            time.sleep(20)
    return call_tool(name, args)


def fetch_all(date):
    cal = call_tool("trading_calendar", {"date": date})
    if not (isinstance(cal, dict) and cal.get("isTradingDay")):
        return None, "非交易日"
    emo = pull_with_retry("short_term_emotion", {"tradeDate": date})
    broken = pull_with_retry("auction_market_scan",
                             {"tradeDate": date, "sortBy": "bidStrength", "limit": 15,
                              "pool": "broken_limit_up_prev", "excludeST": True})
    prev = pull_with_retry("auction_market_scan",
                           {"tradeDate": date, "sortBy": "bidStrength", "limit": 15,
                            "pool": "limit_up_prev", "excludeST": True})
    ladder = call_tool("limit_up_ladder", {"date": date, "maxRowsPerLevel": 40})
    theme = call_tool("theme_intraday_capital",
                      {"tradeDate": date, "universe": "featured", "limit": 10})
    return {"emo": emo, "broken": broken, "prev": prev, "ladder": ladder, "theme": theme}, None



def main():
    tz = zoneinfo.ZoneInfo("Asia/Shanghai")
    date = datetime.datetime.now(tz).strftime("%Y-%m-%d")
    now_hm = datetime.datetime.now(tz).strftime("%H:%M")
    if not DRY and "--force" not in sys.argv and not ("09:27" <= now_hm <= "09:45"):
        print(f"out of push window {now_hm}, skip")
        return
    data, err = fetch_all(date)
    if err:
        print(err)
        return

    emo, broken, prev, ladder, theme = data["emo"], data["broken"], data["prev"], data["ladder"], data["theme"]
    s = emo.get("summary", {})
    sealed, broken_rate = s.get("sealedLimitUp", 0), s.get("brokenBoardRate", 0)
    highest, prom = s.get("highestBoard", 0), s.get("promotionRates", {})
    p1 = prom.get("firstToSecond", 0)
    breadth = s.get("breadth", {})
    up, down = breadth.get("up", 0), breadth.get("down", 0)

    top5 = [r.get("themeName") for r in (theme or {}).get("rows", [])[:5]]
    top3 = [r.get("theme") for r in (ladder or {}).get("primaryThemeStats", [])[:3]]
    ladder_rows = {r.get("code"): r for r in (ladder or {}).get("rows", [])}

    actionable = sealed >= 30 and p1 >= 15 and up > down
    env_line = f"涨{up}/跌{down},涨停{sealed},1进2晋级{p1}%,最高{highest}板,炸板率{broken_rate}%"

    def themes_of(stock):
        ts = set(stock.get("themes") or [])
        lr = ladder_rows.get(stock.get("code"), {})
        ts.add(lr.get("primaryTheme", ""))
        ts.update(lr.get("conceptTags") or [])
        return {t for t in ts if t}

    def is_mainline(stock):
        ts = themes_of(stock)
        return bool(ts & set(top5)) or bool(ts & set(top3))

    def grade(stock):
        cr = stock.get("changeRate", 999)
        sig = stock.get("openBidSignal")
        ps = stock.get("prevStreak", 0)
        board = ps + 1
        c1 = -3 <= cr <= 5
        c2 = sig == "late_bid_up"
        c3 = is_mainline(stock)
        c4 = board <= 3
        market = stock.get("market", "")
        hits = sum([c1, c2, c3, c4])
        if board >= 5:
            return "B", f"{board}板高标只作标杆"
        if cr > 5:
            return "B", f"高开{cr:.2f}%不追"
        if sig == "late_bid_down":
            return "B", "尾撤"
        # v6 市场限制
        if c1 and c2 and c3 and c4:
            if market in ("main_sh", "main_sz"):
                return "S", "5条全满足"
            if market == "gem":
                vr = stock.get("volumeRatio", 0)
                if vr >= 20 and top3 and themes_of(stock) & {top3[0]}:
                    return "S", "创业板破格:量比≥20+第一题材"
                return "A", f"创业板量比{vr}<20按v6降A"
            if market == "star":
                return "A", "科创板最高A"
        if hits >= 3:
            return "A", f"满足{hits}条"
        if hits == 2:
            return "A", f"满足{hits}条"
        return "B", "记录"

    s_list, a_list, b_list, board_list = [], [], [], []
    seen = set()
    for pool, tag in ((prev, "昨涨停"), (broken, "昨炸板")):
        for r in (pool or {}).get("rows", [])[:15]:
            code = r.get("code")
            if code in seen:
                continue
            seen.add(code)
            g, note = grade(r)
            ref = round(r.get("limitUpPrice", 0) / (1 + r.get("limitPct", 10) / 100) * (1 + r.get("changeRate", 0) / 100), 2)
            item = {"code": code, "name": r.get("name"), "ref": ref,
                    "cr": r.get("changeRate"), "op": r.get("openBidPct"),
                    "vr": r.get("volumeRatio"), "ps": r.get("prevStreak", 0), "note": note,
                    "themes": list(themes_of(r)), "tag": tag, "g": g}
            if g == "S":
                s_list.append(item)
            elif g == "A":
                a_list.append(item)
            else:
                b_list.append(item)
            # 打板候选收集(仅昨涨停池)
            if tag == "昨涨停":
                cr, vr = r.get("changeRate", 0), r.get("volumeRatio", 0)
                if r.get("isLimitUpOpen"):
                    board_list.append({"name": r.get("name"), "code": code,
                                       "kind": "一字", "cr": cr, "vr": vr,
                                       "seal": (r.get("limitBuyAmountAfter920") or 0) / 1e8,
                                       "ps": r.get("prevStreak", 0),
                                       "themes": list(themes_of(r)),
                                       "score": 10 + (r.get("limitBuyAmountAfter920") or 0) / 1e10})
                elif 5 <= cr <= 9.9 and (vr or 0) >= 10:
                    sc = 3 if r.get("prevStreak", 0) + 1 <= 2 else (2 if r.get("prevStreak", 0) + 1 == 3 else 1)
                    if themes_of(r) & set(top5) | themes_of(r) & set(top3):
                        sc += 1
                    if (vr or 0) >= 20:
                        sc += 1
                    if r.get("openBidSignal") == "late_bid_down":
                        sc -= 1
                    board_list.append({"name": r.get("name"), "code": code,
                                       "kind": "高开", "cr": cr, "vr": vr,
                                       "seal": 0, "ps": r.get("prevStreak", 0),
                                       "themes": list(themes_of(r)), "score": sc})

    s_list = sorted(s_list, key=lambda x: -x.get("vr", 0))[:2]
    # A级按优先级排序:主线命中优先,其次量比
    main_top = set(top5) | set(top3)
    a_list = sorted(a_list, key=lambda x: (-(bool(set(x.get("themes", [])) & main_top)), -(x.get("vr") or 0)))

    lines = []
    lines.append(f"**【竞价扫描】{date} 开盘扫描(9:27速推·v8规则引擎)**")
    if actionable:
        lines.append(f"**今日环境:可操作日 ✅** — {env_line} → 模型A+C")
    else:
        lines.append(f"**今日环境:不可操作日 ⚠️** — {env_line} → 门禁:涨停≥30且晋级≥15%且涨>跌")
    lines.append("**资金主线** TOP5:" + " / ".join(top5) + " | 涨停题材TOP3:" + " / ".join(top3))
    if s_list:
        lines.append("**S级**:")
        for x in s_list:
            lines.append(f"- {x['name']}({x['code']}) 竞价{x['cr']:.2f}% 尾抢{x['op']}% 量比{x['vr']} {x['tag']} — {x['note']};参考价{x['ref']}")
    else:
        lines.append("**S级:无**")
    if a_list:
        lines.append("**A级**:")
        for x in a_list[:6]:
            lines.append(f"- {x['name']}({x['code']}) 竞价{x['cr']:.2f}% {'尾抢' if x['op'] and x['op']>0 else '无尾抢'} 昨{x['ps']}板 — {x['note']}")
    else:
        lines.append("**A级:无**")
    if b_list:
        lines.append("**B级观察**:" + "、".join(f"{x['name']}" for x in b_list[:8]))

    # —— 综合介入顺序(S级+竞价池候选合并打分排序) ——
    main_top_set = set(top5) | set(top3)
    def inter_score(x):
        sc = {"S": 5, "A": 3}.get(x["g"], 1)
        if x.get("op") and x["op"] > 0:
            sc += 1          # 尾秒抢筹
        if set(x.get("themes", [])) & main_top_set:
            sc += 1          # 主线命中
        if (x.get("vr") or 0) >= 10:
            sc += 1          # 量比放大
        if (x.get("cr") or 0) < 0:
            sc += 0.5        # 低开=低吸优势
        if x.get("ps", 0) >= 4:
            sc -= 1          # 高标减分
        return sc
    order_cand = []
    for x in s_list + a_list:
        if (x.get("cr") or 0) >= 9.9:   # 一字/涨停开不可介入
            continue
        order_cand.append((inter_score(x), x))
    order_cand.sort(key=lambda t: -t[0])
    if order_cand:
        lines.append(f"**【综合介入顺序】**(S级+竞价池合并排序,{'介入' if actionable else '观察'}(今日{'可操作' if actionable else '不动作'}))")
        for i, (sc, x) in enumerate(order_cand[:8], 1):
            tags = []
            if x.get("op") and x["op"] > 0: tags.append("尾抢")
            if set(x.get("themes", [])) & main_top_set: tags.append("主线")
            tags.append(f"量比{x.get('vr', 0)}")
            lines.append(f"{i}. {x['name']}({x['code']}) 参考{x['ref']} — {x['g']}级 {','.join(tags)} 分{sc};回踩{x['ref']}不破低吸,破{x['ref']*0.97:.2f}止损")

    # —— 打板排序(仅打板资金) ——
    if board_list:
        board_list.sort(key=lambda x: -x["score"])
        lines.append("**【打板排序】**(仅打板资金参与,低吸者一律不碰)")
        for i, x in enumerate(board_list[:6], 1):
            if x["kind"] == "一字":
                g = "S级"
                lines.append(f"{i}. {g} {x['name']}({x['code']}) 涨停开一字 委买{x['seal']:.1f}亿 昨{x['ps']}板 — 排板(买不进,挂单等炸板回封)")
            else:
                g = "A级" if x["score"] >= 4 else "B级"
                lines.append(f"{i}. {g} {x['name']}({x['code']}) 竞价+{x['cr']:.1f}% 量比{x['vr']} 昨{x['ps']}板 — 打板观察(秒封才上,炸板走人)")
        lines.append("打板优先级:" + " > ".join(x["name"] for x in board_list[:5]))

    # —— 出手清单·总结排序(按优先级排序,30秒完成决策) ——
    lines.append("**【操作总结·出手清单】(按优先级排序)**")
    if not actionable:
        lines.append("- 今日不动作:空仓观望(门禁:涨停≥30且晋级≥15%且涨>跌)")
        if a_list:
            lines.append("- 明日优先观察:" + " > ".join(f"{x['name']}" for x in a_list[:4]))
        lines.append("- 回避:" + "、".join(f"{x['name']}" for x in b_list[:4]) + "(一字/高开/高标)")
        lines.append("- 今日核心动作:空仓防守,等修复日;持仓票反弹减仓不补")
    else:
        # 可操作日:完整出手清单
        top_s = s_list[0] if s_list else None
        lines.append("- 低吸首选:" + (f"{top_s['name']}(回踩{top_s['ref']}不破,买入≤竞价价+1%;出场:尾盘≥3%减半/次日+2%不封走/破买价3%止损)" if top_s else "无"))
        board_watch = [x for x in b_list if 5 <= (x.get("cr") or 0) <= 8 and (x.get("vr") or 0) >= 10]
        lines.append("- 打板观察:" + (" > ".join(f"{x['name']}({x['cr']:.1f}%+量比{x['vr']})" for x in board_watch[:3]) if board_watch else "无") + "(仅打板资金,低吸不买)")
        giveup = [x for x in a_list if x.get("vr", 0) < 10]
        lines.append("- 放弃:" + ("、".join(f"{x['name']}(量比不足/题材弱)" for x in giveup[:4]) if giveup else "无"))
        lines.append("- 回避:" + "、".join(f"{x['name']}" for x in b_list[:4]) + "(一字/高开/高标)")
        lines.append("- 今日核心动作:低吸" + (top_s['name'] if top_s else "待确认") + ",打板看" + (board_watch[0]['name'] if board_watch else "无") + ";仓位≤5成")
    text = "\n".join(lines)
    print(text)

    if DRY:
        print("\n[dry-run] 未发送")
        return

    # 防重复:今日marker已存在则跳过(本机与云端并发时后到者退出)
    try:
        _pat = os.environ.get("GH_PAT") or open("C:/Users/xy/.github_pat", encoding="utf-8").read().strip()
        _req = urllib.request.Request(f"{GH_API}/contents/push_history/{date.replace('-', '')}.json",
                                      headers={"Authorization": f"Bearer {_pat}",
                                               "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(_req, timeout=10) as _r:
            _r.read()
        print("marker already exists, skip (dedup)")
        return
    except urllib.error.HTTPError:
        pass  # 404 = 今日未推,继续
    except Exception:
        pass

    # 飞书群 webhook
    ok_fs = False
    try:
        req = urllib.request.Request(FEISHU_WEBHOOK,
                                     data=json.dumps({"msg_type": "text", "content": {"text": text}}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ok_fs = json.loads(r.read().decode()).get("StatusCode") == 0
    except Exception:
        pass
    print("feishu:", ok_fs)

    # QQ 邮件
    try:
        pw = os.environ.get("SMTP_PASS") or open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "smtp_pass.txt"), encoding="utf-8").read().strip()
        html = "<pre style=\"white-space:pre-wrap;font-family:inherit;font-size:14px\">" + text + "</pre>"
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = Header(f"【竞价扫描】{date} 开盘扫描", "utf-8")
        msg["From"] = formataddr((str(Header("竞价扫描", "utf-8")), MAIL_ADDR))
        msg["To"] = MAIL_ADDR
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as sm:
            sm.login(MAIL_ADDR, pw)
            sm.sendmail(MAIL_ADDR, [MAIL_ADDR], msg.as_string())
        print("mail: OK")
    except Exception as e:
        print("mail fail:", e)

    # GitHub marker
    try:
        pat = os.environ.get("GH_PAT") or open("C:/Users/xy/.github_pat", encoding="utf-8").read().strip()
        rec = {"date": date, "stocks": [
            {"code": x["code"], "name": x["name"], "grade": x["g"], "refPrice": x["ref"],
             "prevClose": round(x["ref"] / (1 + x["cr"] / 100), 2), "signals": x["note"],
             "note": x["tag"], "watchBuy": False} for x in s_list + a_list]}
        b64 = base64.b64encode(json.dumps(rec, ensure_ascii=False).encode()).decode()
        d8 = date.replace("-", "")
        req = urllib.request.Request(f"{GH_API}/contents/push_history/{d8}.json",
                                     data=json.dumps({"message": f"record: {d8} fast",
                                                      "content": b64}).encode(),
                                     headers={"Authorization": f"Bearer {pat}",
                                              "Accept": "application/vnd.github+json",
                                              "Content-Type": "application/json"},
                                     method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
            print("marker: OK")
        except urllib.error.HTTPError as e:
            if e.code == 422:
                print("marker: exists(skip)")
            else:
                print("marker fail:", e.code)
    except Exception as e:
        print("marker fail:", e)


if __name__ == "__main__":
    import logging
    try:
        logging.basicConfig(filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fast_push_log.txt"),
                            level=logging.INFO, format="%(asctime)s %(message)s")
        logging.info("task fired, args=%s", sys.argv[1:])
    except Exception:
        pass
    main()
