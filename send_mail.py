# -*- coding: utf-8 -*-
"""发送竞价扫描 HTML 邮件(QQ SMTP)。
用法: python send_mail.py /tmp/auction.html
环境变量: SMTP_PASS (QQ邮箱SMTP授权码)
"""
import os
import smtplib
import sys
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

html = open(sys.argv[1], encoding="utf-8").read()
passwd = os.environ.get("SMTP_PASS", "")
if not passwd:
    sys.exit("SMTP_PASS 未设置")

subject = "【竞价扫描】" + os.environ.get("DATE_STR", "") + " 开盘扫描"
msg = MIMEText(html, "html", "utf-8")
msg["Subject"] = Header(subject, "utf-8")
msg["From"] = formataddr((str(Header("竞价扫描", "utf-8")), "215477645@qq.com"))
msg["To"] = "215477645@qq.com"

with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as s:
    s.login("215477645@qq.com", passwd)
    s.sendmail("215477645@qq.com", ["215477645@qq.com"], msg.as_string())
print("OK mail sent")
