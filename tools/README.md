# tools/README.md

**职责**：质量保障与隐私防护脚本，不参与运行时，仅供开发/发布使用。

## 关键文件
| 文件 | 作用 |
|---|---|
| `selftest_lite.py` | 工程自检（114+ 项断言），改完必跑；含 **pyflakes 静态 lint 闸门** |
| `smoke_test.py` | 接口冒烟（40+ 项，覆盖分类/状态位/回收站/黑名单/订阅全链路） |
| `smoke_real_download.py` | **真实下载冒烟**（网络/IO 链路改动必跑） |
| `verify_live.py` | 实机端到端（启动→功能→重启持久化） |
| `test_reader_logic.js` / `test_library_drag_logic.js` | node 纯逻辑单测（48 项） |
| `test_frontend_bundle.js` | 前端模块束冒烟：最小 DOM 桩真实加载 7 个模块，抓漏带前导依赖 |
| `test_progress_model.py` | 下载进度契约（直驱回调，零网络零 fake） |
| `bench_download.py` | 下载速度基准 |
| `privacy_scan.py` / `install_hooks.py` | 提交前隐私扫描 / 装 pre-commit 钩子（换机须重跑） |

## 约定
- **跑测试用公共环境**：`D:\code\app\Miniconda3\envs\test\python.exe tools\selftest_lite.py`
  （本项目**没有** `.venv-build`——那是打开发版时才需要的构建 venv，见 ARCHITECTURE §3；测试不需要它）
- 一律以**退出码**判定成败，禁止看输出片段判绿；node 不在 PATH，用完整路径调用。
- **静态校验用工具，不用文本断言**：源码里「字符串在不在」查不出符号未导入（曾因此漏掉 `library.py` 少 import 的 `NameError`）。`selftest_lite.py` 已内建 pyflakes 闸门，装了 pyflakes 就必须零告警。

## 坑
- 打桩必须断言 `stub_ran`，否则会静默 fallback 成真实下载；判定「已下载」要 `os.walk` 只数文件（jmcomic 会先建空壳目录）。
- 改文件换行符前先确认项目主流取向：本仓库统一 **LF**（`.gitattributes` 已锁），批量改写脚本务必显式带 `newline="\n"`，否则会产生整文件 diff。
