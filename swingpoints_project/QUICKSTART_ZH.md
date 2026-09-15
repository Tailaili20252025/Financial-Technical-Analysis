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

## 4. 打开可操作的窗口

```bash
python app.py --gui data/data.csv
```

你可以在窗口里选文件、修改 Window、切换检测依据，并导出结果。
如果提示 Tkinter 或显示环境不可用，先使用第 3 步生成图片。
开发环境没有图形显示器，因此窗口点击操作尚未现场验证；命令行流程已测试。

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
