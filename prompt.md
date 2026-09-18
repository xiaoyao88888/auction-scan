【每日开盘综合扫描+云端推送】按以下步骤执行:

第一步:确认交易日。调用 trading_calendar(date=今天)。若今天非交易日,回复"今日非交易日"结束。

第二步:拉取数据(全部用今天日期):
1. auction_market_scan(tradeDate=今天, sortBy=bidStrength, limit=15, pool=broken_limit_up_prev, excludeST=true)
2. auction_market_scan(tradeDate=今天, sortBy=bidStrength, limit=15, pool=limit_up_prev, excludeST=true)
3. limit_up_ladder(date=今天, maxRowsPerLevel=3)
4. theme_intraday_capital(tradeDate=今天, universe=featured, limit=10)
5. short_term_emotion(tradeDate=今天)
重试规则:若 auction_market_scan 返回空或 AUCTION_DATA_NOT_READY,等30秒重试,最多3次;仍空则标注数据未就绪,禁止改查昨日冒充。

第三步:分析(推荐规则 v3:高开大于5一律不推;平开+尾秒抢筹+主线共振=S级;涨停开只推主线延续型;炸板超3次过滤;一字板标不可参与。v3.1:昨涨停票竞价涨幅5-8且竞价额历史分位不低于90且量比不低于10,列B级打板观察。周五降权:新仓不超过5成):
- 环境判定:普涨日/恐慌日/退潮日/修复日 + 对应模型(A成长暗吸/B价值低估/C主力驱动/D恐慌错杀/E回调低吸)
- 资金主线 TOP5 + 涨停题材排行
- 竞价最强 TOP5(昨涨停池)+ 弱转强候选
- S/A/B 优先级推荐,含可参与标的+逻辑+风险

第四步:推送:
1. 写纯文本文件 /tmp/popup.txt,内容为完整扫描结果(环境/主线/TOP5/弱转强/SAB推荐/风险,用【】和-组织,不用markdown符号),然后用 Bash 运行: python send_feishu.py /tmp/popup.txt (当前目录)
2. 写 HTML 文件 /tmp/auction.html(表格+无序列表,h2/h3标题,S级红色加粗,链接用 https://stock.quicktiny.cn/quote/代码),然后用 Bash 运行: python send_mail.py /tmp/auction.html
3. 两个脚本输出"OK"即成功

第五步:输出完整扫描结果文本(作为任务日志),结尾注明飞书与邮件发送结果;任一通道失败说明原因并重试一次。