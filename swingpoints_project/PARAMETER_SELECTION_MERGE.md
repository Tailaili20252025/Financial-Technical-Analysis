# Merge the parameter-selection addition

This is a **changes-only** package against the uploaded `Financial-Technical-Analysis-main (1)(1).zip`. It needs the existing unified application, its backtest module and installed requirements. It is not a standalone replacement project.

## GitHub upload

1. Unzip `SwingPoints_Parameter_Selection_Changes_Only.zip`.
2. In GitHub, open your repository root and select the branch you will merge into main.
3. Choose **Add file → Upload files**.
4. From the unzipped package, drag the **one `swingpoints_project` folder** onto that root upload page. Do not first enter the existing `swingpoints_project` directory; that would add an unwanted extra folder level.
5. Confirm paths start with `swingpoints_project/optimize_parameters.py`, `swingpoints_project/swingpoints/parameter_selection.py`, etc. There should not be `swingpoints_project/swingpoints_project/`.
6. Commit and open the PR. Suggested text is in `PARAMETER_SELECTION_PR.md`.

Files at matching paths update their existing counterparts; new paths are added. The only existing file changed is the project `README.md`, which gains a link and a run command. All existing application Python files, tests, `data.csv`, GUI settings and old outputs remain unchanged. If your README has changed since the uploaded ZIP, retain your new material and add only the parameter-selection section.

`PARAMETER_CHANGES_MANIFEST.json` records every payload file, its hash, whether it is new or modified, and the exact baseline ZIP hash. No deletion is required. The manifest excludes its own checksum.

## Local installation

Merge the contents of the supplied `swingpoints_project` into your existing folder of the same name. Do not delete and replace the existing directory: this archive contains only additions and one modified README.

Then open a terminal in that existing project folder:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python optimize_parameters.py --plan parameter_search_plan.json --output parameter_results/my_search --workers 4
```

The completed reference run is already provided, so rerunning is optional. Start with `parameter_results/reference/RESULTS.md`. Data and outputs use relative paths and work after the folder is merged.

## 中文说明

解压后，把这一层 `swingpoints_project` 上传到 GitHub **仓库根目录**。不要进入仓库里面已有的 `swingpoints_project` 后，再拖入同名文件夹，否则会嵌套一层。

这是增量包，不能当成完整项目单独运行，也不要删除原项目后再放进去。它增加参数搜索代码、60只股票的数据、完整结果和说明；现有程序的默认参数不会被自动替换。实际搜索结果没有证明盈利能力稳定提升，因此选出的参数只作为可复现的研究配置。
