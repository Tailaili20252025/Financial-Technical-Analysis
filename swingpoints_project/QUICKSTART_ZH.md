# Step 3 更新提示

程序现在会自动计算和绘制趋势线，原来的运行命令仍可使用。
详见 [STEP3_ZH.md](STEP3_ZH.md) 的中文说明。每次运行现在输出六个文件，
新增 `trendlines.csv` 和 `trendlines.json`。旧 `examples`/`output` 内容是历史结果；
新示例在 `examples/step3_close_window2` 和 `examples/step3_high_low_window5`。

# 如何运行和理解这个程序

这个任务只完成老师 PDF 的前两步：读取数据并画价格图，计算并显示 Swing High / Low。
这一步还不需要训练机器学习模型，也不会预测下一分钟价格。

## 1. 下载并解压

解压 `SwingPoints_Project.zip`，进入 `swingpoints_project` 文件夹。
里面已经包含你的 `data/data.csv`，以及同一份数据转换的 `data/data.json`。

## 2. 在 Mac 上安装依赖

需要 Python 3.10 或更新版本。在终端输入 `python3 --version` 检查版本。
在终端输入 `cd `（注意后面有空格），把解压后的 `swingpoints_project`
文件夹拖入终端，再按回车。这样终端就进入了项目文件夹。

然后依次执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`.venv` 是这个项目自己的 Python 环境。以后重新打开终端运行项目时，
进入同一文件夹，再执行 `source .venv/bin/activate` 即可。
Windows 命令见英文 README。

## 3. 先运行最简单的版本

```bash
python app.py data/data.csv
```

程序会生成 `output` 文件夹。打开里面的 `prices.png` 就能看到结果。
默认计算结果为 49 个 swing highs 和 52 个 swing lows。

- 蓝色线：Close。
- 浅棕色线：High。
- 灰蓝色线：Low。
- 红色向下三角：swing high 原来发生的位置。
- 绿色向上三角：swing low 原来发生的位置。
- 小叉号：这个转折点什么时候才被确认；纵坐标仍是原转折点的价格。

`swing_points.csv` 可以用 Excel 打开，查看每个点的价格、发生时间和确认时间。
`pivot_bar` 是从 1 开始的行号，`confirmed_bar` 是第一次能够确认的行号。

JSON 输入运行方法：

```bash
python app.py data/data.json --output output/json
```

## 4. GUI：Tkinter 安装与使用

在包含 `app.py` 的 `swingpoints_project` 文件夹打开终端。
如果已经创建虚拟环境，依次运行：

```bash
source .venv/bin/activate
python -m tkinter
```

出现小测试窗口说明 Tkinter 可用。关闭测试窗口，再启动程序：

```bash
python app.py --gui data/data.csv
```

也可以运行 `python app.py --gui`，然后点击 **Open CSV / JSON** 选文件。
读取文件后会自动完成 Step 1–3，并显示全部数据的分析结果。

1. **Window**：拐点左右各比较多少条数据，默认 2，不一定是两分钟。
2. **Swing basis**：`close` 用收盘价；`high-low` 用最高价找高点、最低价找低点。
3. **Observed bars**：只分析从头开始的前 N 条数据。输入 100，点击
   **Apply / replay**，就只显示当时能够确认的结果。
4. **Next bar**：再增加一条已观察数据并重新分析。读入文件时已显示全部数据，
   因此要先减少 Observed bars 才能逐步回放。
5. 趋势线设置依次是：容差百分比、向前考虑的同类 swing 数量、最少触点、
   每个方向最多显示几条线。默认分别为 0.5、20、2、3。
6. 下方两个标签页分别列出已确认的 swing points 和图中选中的 trendlines。
7. 修改设置后先点击 **Apply / replay**，再点 **Export visible results**，
   选择已建好的结果文件夹。保存的是上一次成功显示的结果，包括 PNG、
   swing CSV/JSON、trendline CSV/JSON、run_summary.json 共六个文件。
   不同数据请选择不同文件夹，同名结果文件会被覆盖。

如果提示找不到 `tkinter` / `_tkinter`，不要运行 `pip install tkinter`。
Mac 可安装 python.org 提供的带 Tcl/Tk 的 Python。在旧虚拟环境外，先确认
新解释器的 `python3 -m tkinter` 能打开测试窗口，再建立新环境：

```bash
python3 -m venv .venv-tk
source .venv-tk/bin/activate
python -m pip install -r requirements.txt
python app.py --gui data/data.csv
```

使用不带 Tk 的同一个 Python 重建环境不能解决这个问题。若终端提示
`python: command not found`，先激活环境；若找不到 `app.py`，先进入项目目录。
GUI 需要本地图形桌面；没有显示环境时仍可以用命令行导出图片。

`gui.py` 中的 `SwingApp` 保存界面状态，按钮通过 `command=...` 调用相应方法，
`StringVar` 保存输入框内容，Matplotlib 的 canvas 显示图形。当前分析在主线程
同步执行，大数据运行期间窗口可能暂时不响应。开发环境未实际点击测试 GUI。
英文安装说明、全部控件说明和排错见 [README 第 2 节](README.md#2-gui---tkinter-usage-and-install)。

## 5. Window 是什么意思

默认 `window=2`：一个点必须高于左边 2 个点和右边 2 个点，才能算高点；
低点的判断方向相反。全部是严格比较，相等的峰顶暂不算。

例如，第 10 分钟看起来是高点，但还需要第 11、12 分钟的数据。
所以程序只能在第 12 分钟结束后确认，并同时记录：

- 高点发生在第 10 分钟。
- 确认发生在第 12 分钟。

程序没有声称第 10 分钟当时就知道答案。这是避免提前看未来的关键。

切换到更大的窗口：

```bash
python app.py data/data.csv --window 5 --output output/window5
```

默认是在 Close 上找转折点，与老师 PDF 的价格图对应。
如果你想在 High 上找高点、在 Low 上找低点：

```bash
python app.py data/data.csv --basis high-low --window 5 --output output/high_low
```

老师 PDF 没有指定具体窗口，因此数量取决于窗口和检测依据，不要求与示意图完全相同。
这里的“确认”表示等待左右窗口完整，不包含之前报告提过的额外突破确认条件。

## 6. 只看前 100 分钟，模拟当时不知道后面的数据

```bash
python app.py data/data.csv --until 100 --output output/first100
```

只显示前 100 根 K 线，以及在这之前已经确认的 swing points。
窗口中也可以把 Observed bars 改为 100，点击 Apply / replay，再点击 Next bar
逐条揭开数据，观察新转折点如何出现。

## 7. 运行测试

```bash
python -m unittest discover -s tests -v
```

看到 `Ran 34 tests` 和 `OK` 表示自动化检查通过。测试包括：
已知例子的高低点、确认延迟、读取两种格式、错误数据处理，以及追加未来数据
后不能改写此前已确认事件。

## 8. 从哪里开始看代码

先看 `app.py` 的 main 函数：读取数据、计算点、画图、导出。
然后看 `swingpoints/data.py` 的 load_prices，最后看
`swingpoints/detector.py` 的 update。每到一根新 K 线，update 只检查
目前已经完整出现的一个局部窗口，不访问未到来的数据。

提交记录在随附的 `swingpoints.bundle` 中。英文 README 有恢复 Git 仓库的命令。
