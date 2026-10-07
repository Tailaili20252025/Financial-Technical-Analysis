# Step 5–6 使用说明

## 先运行

终端先进入含有 `app.py` 的 `swingpoints_project` 文件夹。已经有虚拟环境时：

```bash
source .venv/bin/activate
python app.py data/data.csv --output output
```

新解压的文件夹没有虚拟环境时，先执行一次：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py data/data.csv --output output
```

会自动依次执行 Step 1–6，并计算已有八种指标。结果在 `output`。
其中 `trades.png` 是入场／止盈／止损图，`equity.png` 是账户盈亏图。

## 图形界面

```bash
python -m tkinter
python app.py data/data.csv --gui
```

第一条是 Tk 安装检查，关闭小测试窗口后运行第二条。

- **Step 5–6 settings**：改仓位、初始资金、ATR 周期、止损倍数、盈亏比、费用等。
- **Trade chart**：所有交易的 Buy/Sell、入场价、止损价和止盈价。
- **Equity / P&L**：账户价值、已实现盈亏、浮动盈亏和回撤。
- **Steps 5–6: trades**：具体交易表。双击一行，只看这笔交易的图。
- **Entry decisions**：解释为什么一个确认信号未交易，例如已有持仓或 ATR 尚未形成。
- **Observed bars → Apply / replay → Next bar**：逐根回放。弹出的图是快照，推进后重新打开图查看最新结果。
- **Export visible results**：导出当前已成功计算的结果，共 20 个文件。

## 和图片一致的逻辑

确认突破下降阻力线 → **Buy / 做多**。确认跌破上升支撑线 → **Sell / 做空**。
Sell 在这里是建立空头，因此之后价格跌才盈利，不是简单卖出现有股票。
同时最多持有一笔交易，多条线同时同方向确认只产生一笔。

默认按图片在“确认这一根的 Close”模拟入场。这是用于演示的理想成交假设，
不是在最初 crossing 那一根回填入场，也不是按趋势线上的预计价格成交。
报告推荐的下一根 Open 入场可以这样比较：

```bash
python app.py data/data.csv --entry-timing next_open --output next_open_results
```

图片没有规定止损和止盈具体隔多远，因此按报告使用确认时 ATR：
每单位止损距离 R = 2 × ATR(14)，止盈距离 = 2 × R。

| 方向 | 止损 | 止盈 | 盈亏（未扣费用） |
| --- | --- | --- | --- |
| Buy / 多头 | 入场价 − R | 入场价 + 2R | 数量 ×（退出价 − 入场价） |
| Sell / 空头 | 入场价 + R | 入场价 − 2R | 数量 ×（入场价 − 退出价） |

入场后两个价格固定，之后 ATR 变化也不移动。默认只在止损或止盈触发时退出。
可以选择报告中的“假突破后退出”或“反向信号后退出”，会在下一根 Open 平仓。
不会利用未来才知道的假突破标签删除之前的交易。

同一根 High/Low 同时碰到止盈和止损且无法知道先后时，保守采用止损优先，
并标记 `ambiguous_exit`。跳空超过止损时按 Open 模拟成交，可能亏得更多。
Close 入场的当根 High/Low 已经发生，不能用来假装入场后已经止盈或止损。

数据结束还未退出的交易保持 open；浮动盈亏单独显示，不算作已实现收益。
默认每次 1 单位、初始资金 10,000、零手续费／滑点／借券费，可在设置中修改。
原始 data.csv 没有 Volume，VWAP 仍会显示 unavailable，其他功能正常。

## 上传到 GitHub

已有本次提供的 main 版本时，解压 `Step56_Changes_Only.zip`。
进入仓库**根目录**（能看到 `swingpoints_project` 的那一层）及目标分支，
选择 **Add file → Upload files**，把解压后的内容拖入，再提交。
路径相同的文件会被更新，新增模块和结果会被加入。

不要把整个 ZIP 当成源码上传，也不要在 `swingpoints_project` 内再套一层同名文件夹。
完整项目 ZIP 用来直接下载运行；changes-only ZIP 用来更新你这次上传给我的代码版本。
只有 changes-only 文件不能单独运行；它需要覆盖到原项目上。

英文完整规则、参数定义和文件说明见 `STEP56.md`；本次数据结果见 `STEP56_RESULTS.md`。
