【A股收盘复盘】生成今日收盘复盘报告并推送。

第一步:确定复盘日期。若环境变量 FORCE_DATE 非空,用 FORCE_DATE 作为复盘日期(标注为测试);否则用今天,先调用 trading_calendar(date=今天),非交易日则回复"今日非交易日"结束。

第二步:数据采集(复盘日期简称 D,全部用该日期):
1. index_market(symbols=上证指数,深证成指,创业板指,科创50, tradeDate=D) 或 index_market mode=snapshot → 指数收盘与涨跌幅、两市成交额(summary.marketTurnover)
2. market_overview(date=D) → 涨跌家数、市场温度
3. limit_stats(date=D) → 涨停/跌停/炸板/封板率
4. limit_up_ladder(date=D, maxRowsPerLevel=8) → 梯队结构、题材排行、晋级率、各板封板时间/换手/成交额
5. board_break_analysis(tradeDate=D) → 断板率、高标杀、断板去向
6. limit_up_premium(startDate=D前一天, endDate=D前一天) → 昨日涨停今日均涨
7. sector_analysis(source=kpl, period=60, strengthPeriod=5) → 板块四象限
8. capital_flow(flowType=market, date=D) → 主力/超大单/大单/中单/小单净额
9. theme_intraday_capital(tradeDate=D, universe=featured, limit=15) → 板块主力净流入TOP15
10. cls_news(date=D, limit=30) + WebSearch(今日政策/产业要闻) → 今日核心催化
11. market_catalyst_calendar(startDate=D次日, endDate=D+7天) + macro_calendar → 明日关注事件
12. kline(codes=全部3板以上+2板股票代码数组, days=151, maxRows=150) → 计算每只票近150日阶段高点,与今日最高价对比判定是否阶段新高
13. anomaly_detection(date=D) + official_announcements(keywords=异常波动,停牌核查, days=30) → 监管异动排查

数据引用铁律:所有数字从工具字段直接复制,禁止编造;搜不到标"未获取"。

第三步:按14个章节模板生成报告(与用户模板一致):
① 市场全景:指数表格(收盘/涨跌幅)、成交额与放缩量、涨跌家数、市场温度、一句话定性
② 涨跌停与情绪:涨停/跌停/炸板/封板率/昨日涨停今日均涨表格+情绪读数
③ 连板梯队+晋级率:梯队表格(高度/家数/代表个股)+晋级率表格+解读
④ 断板分析:断板率、高标杀名单、断板去向、结论
⑤ 赚钱效应:涨停溢价、普涨面、封板质量、小单流出解读、一句话
⑥ 涨停密集板块排行:表格(排名/板块/涨停家数/最高连板/代表个股)+看点
⑦ 板块轮动四象限:表格(象限/板块/今日涨幅/近5日/60日)+核心判断3条
⑧ 资金流向:全市场表格+板块TOP15表格+关键结论
⑨ 今日核心催化:政策端/产业与商品端/海外端/盘面焦点,编号+来源链接
⑩ 明日关注:下一交易日日期+必须盯的事件编号列表+重点跟踪方向
⑪ 3板以上+2板逐只拆解:每只票(题材/封板类型/封板时间/成交额/换手率/拆解点评),2板用表格
⑫ 历史新高分析:口径说明+核验表格(今日最高/150日阶段高点/是否新高)+结论(含"修复而非突破"判断)
⑬ 复盘总结:一句话定性+三条主线逻辑+风险提示+操作建议(仓位/方向/节奏)
⑭ 监管异动排查:核查情况+高风险名单表格+排查建议
结尾加免责声明:本复盘基于当日收盘公开数据整理,仅供研究参考,不构成投资建议。

第四步:推送:
1. 报告写入 /tmp/closing.txt(纯文本)
2. Bash 运行: python send_feishu.py /tmp/closing.txt
3. 报告写入 /tmp/closing.html(HTML 表格版),Bash 运行: export DATE_STR=<复盘日期> && export SUBJECT_PREFIX=【收盘复盘】 && python send_mail.py /tmp/closing.html
4. 输出完整报告文本作为日志;任一通道失败重试一次