# -*- coding: utf-8 -*-
"""发送纯文本消息到飞书自定义机器人 webhook。
用法: python send_feishu.py /tmp/popup.txt
环境变量: FEISHU_WEBHOOK
"""
import os
import sys
import urllib.request

WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
if not WEBHOOK:
    sys.exit("FEISHU_WEBHOOK 未设置")

text = open(sys.argv[1], encoding="utf-8").read()
payload = {"msg_type": "text", "content": {"text": text}}
req = urllib.request.Request(
    WEBHOOK,
    data=__import__("json").dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    body = resp.read().decode("utf-8")
print("OK feishu:", body[:80])
