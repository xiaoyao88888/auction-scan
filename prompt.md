【每日开盘综合扫描+云端推送】按以下步骤执行,输出必须严格遵守固定模板与评分细则:

第一步:确认交易日。调用 trading_calendar(date=今天)。若今天非交易日,回复"今日非交易日"结束。

第二步:拉取数据(全部用今天日期):
1. auction_market_scan(tradeDate=今天, sortBy=bidStrength, limit=15, pool=broken_limit_up_prev, excludeST=true)
2. auction_market_scan(tradeDate=今天, sortBy=bidStrength, limit=15, pool=limit_up_prev, excludeST=true)
3. limit_up_ladder(date=今天, maxRowsPerLevel=3)
4. theme_intraday_capital(tradeDate=今天, universe=featured, limit=10)
5. short_term_emotion(tradeDate=今天)
重试规则:若 auction_market_scan 返回空或 AUCTION_DATA_NOT_READY,等30秒重试,最多3次;仍空则标注数据未就绪,禁止改查昨日冒充。

【数据引用铁律】所有数字必须直接从工具返回字段复制:最高板数用 short_term_emotion 的 summary.highestBoard 或 ladder 的 boardSummary;晋级率用 emotionMetrics.promotionRates 的 1to2/2to3 数值;涨跌家数用 summary.breadth;禁止自己推算或改写任何数字。

第三步:环境判定(固定公式,按 breadth 与涨停数):
- 上涨家数/下跌家数 大于3 且 涨停数不小于30 → 普涨日(模型 A+C)
- 上涨家数/下跌家数 大于1.5 且 涨停数10-30 → 修复日(模型 A+C,仓位正常)
- 下跌家数/上涨家数 大于3 → 恐慌日(模型 B+D,禁追高)
- 涨停数小于10 或 最高板低于4 或 1进2晋级率低于5 → 退潮日(不开新仓,只低吸防守)
- 周五:所有新仓建议减半,尾盘不接力

第四步:S/A/B 评分细则(严格执行,不允许凭感觉调级):

S级条件(必须同时满足全部4条):
1. 竞价涨幅 changeRate 介于 -3 与 5 之间(含)
2. openBidSignal = late_bid_up(尾秒抢筹)
3. 主线共振:该股 themes 里至少有一个词命中「当日资金主线TOP5板块名」或「涨停题材排行TOP3(primaryThemeStats前3个theme名)」
4. 连板高度(prevStreak+1)不超过3板

A级条件:满足S级条件中的任意2-3条,或高标票(4板及以上)满足前3条(高标票最高只能到A,且必须标注高位博弈风险)

B级条件:其余值得观察的:一字板(标不可参与)、高开大于5(一律不推,只记录)、昨涨停竞价涨幅5-8且量比不低于10(v3.1打板观察)、5板以上高标(只作标杆不参与)

第五步:推送:
1. 写纯文本文件 /tmp/popup.txt,内容模板固定为:
【竞价扫描】YYYY-MM-DD 周X 开盘扫描
【今日环境】…(含涨跌家数、涨停数、炸板率、最高板、1进2晋级率,数据全部来自工具字段)
【资金主线】TOP5板块名+净额 / 涨停题材TOP3
【竞价最强TOP5】(昨涨停池:名称+代码+竞价涨幅+尾抢信号+量比+连板高度,一字板标不可参与)
【弱转强候选】(昨炸板池:同上格式)
【S/A/B推荐】(S级…/A级…/B级…,每条含可参与标的+逻辑+风险,注明依据上述评分细则哪几条)
【风险提示】…
然后用 Bash 运行: python send_feishu.py /tmp/popup.txt
2. 写 HTML 文件 /tmp/auction.html(与 popup.txt 内容一致,表格+无序列表,h2/h3标题,S级红色加粗,链接用 https://stock.quicktiny.cn/quote/代码),然后用 Bash 运行: python send_mail.py /tmp/auction.html
3. 两个脚本输出"OK"即成功
4. 写推荐记录 JSON 文件 /tmp/record.json,格式:{"date":"YYYY-MM-DD","stocks":[{"code":"600667","name":"太极实业","grade":"S","refPrice":20.56,"prevClose":20.23,"signals":"尾抢+主线","note":"逻辑一句话"}]}。refPrice 用该股当日竞价价(auction_market_scan 的 changeRate 反推:preClose×(1+changeRate/100) 四舍五入两位),包含全部 S 级与 A 级标的(B级不含)。

第六步:输出完整扫描结果文本(作为任务日志),结尾注明飞书与邮件发送结果;任一通道失败说明原因并重试一次。