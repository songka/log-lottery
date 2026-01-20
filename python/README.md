# Python 抽奖程序

本目录提供一个基于 Tkinter 的抽奖桌面应用，用于读取人员名单与奖项配置并进行抽奖。

## 运行方式

1. 确认已安装 Python 3.10+。
2. 进入本目录后执行：

```bash
python app.py
```

首次运行会自动生成默认配置与数据文件（CSV，UTF-8 with BOM，方便 Excel 直接打开）。

## 配置文件说明

默认配置文件为 `config.json`，支持以下字段：

- `participants_file`：人员名单文件路径（CSV/JSON）。
- `prizes_file`：奖项配置文件路径（CSV/JSON）。
- `excluded_file`：排除名单文件路径（CSV/JSON）。
- `output_dir`：输出目录路径。
- `results_file`：结果 JSON 文件名。
- `results_csv`：结果 CSV 文件名。
- `admin_password`：管理员密码（用于查看保底与排除相关配置）。
- `excluded_winners_min`：排除名单最小中奖人数（填 `0` 或 `null` 表示不限制）。
- `excluded_winners_max`：排除名单最大中奖人数（填 `null` 表示不限制）。
  - 该范围统计覆盖所有奖项（包含保底中奖名单）。

## 目录结构

- `app.py`：Tkinter UI 主程序。
- `lottery.py`：抽奖逻辑与数据读写。
- `data/`：默认数据文件目录。
  - `participants.csv`：人员名单。
  - `prizes.csv`：奖项配置。
  - `excluded.csv`：排除名单。
- `output/`：抽奖结果输出目录（自动生成）。

## 功能提示

- 主界面支持设置随机种子。
- “忽略排除名单”复选框用于决定抽奖时是否忽略排除名单。
- 抽奖结果会同步保存到 `output/` 目录的 JSON/CSV 文件中。
- 未登录状态下可正常抽奖，但无法查看保底名单与排除相关配置。
