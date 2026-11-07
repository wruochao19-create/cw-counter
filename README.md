# CW Counter 0.19

Windows 上的 MapleStory Classic World 经验效率与候选击杀统计工具。读取可见画面，自动确认地图、定位经验提示与底部经验条；支持置顶、圆角侧栏、小窗模式、主题和透明度。普通运行离线完成，默认不保存截图。

## 换电脑安装（普通用户）

支持 **Windows 10/11 x64 + Python 3.12 x64**。当前没有独立 EXE，安装后通过本项目自己的虚拟环境启动，不依赖 Codex。

1. 从 [Python 官方下载页](https://www.python.org/downloads/windows/) 安装 Python 3.12 的 Windows x64 installer，保留 Tcl/Tk 与 pip；可勾选添加到 PATH。请使用完整安装版，不使用 embeddable package。
2. 下载仓库 ZIP 或 source.zip，**解压**到有写权限的普通目录，例如 Documents/CW Counter。不要放进游戏目录或 Program Files。
3. 双击 **Setup CW Counter.cmd**。首次需要联网下载依赖，脚本创建本目录 `.venv`、安装固定版本并验证模型和空闲界面。出现 Setup complete 即完成。
4. 双击 **Start CW Counter.cmd**。以后直接用它启动，无需每次安装。

不要把旧电脑的 `.venv` 或 `.deps` 复制过去；重新运行 Setup。安装错误会保留在窗口中。若 ONNX 报 DLL load failure，先确认 Python 为 x64，必要时安装 [Microsoft Visual C++ x64 Runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。

## 给另一台电脑的 agent

直接把仓库和下面这段交给 agent；完整交接见 [AGENT_SETUP.md](AGENT_SETUP.md)。

> 请读取 README.md 和 AGENT_SETUP.md。用完整 Python 3.12 x64 运行 setup_windows.py，创建本地 .venv；运行 .venv/Scripts/python.exe doctor.py 验证离线模型和空闲 UI，然后报告启动命令。不要访问游戏文件、发送输入或自动开始真实计数，不要上传个人设置和记录。

命令行等价操作（PowerShell，在项目根目录）：

```powershell
py -3.12 setup_windows.py
.\.venv\Scripts\python.exe doctor.py
.\.venv\Scripts\python.exe app.py
```

安装阶段联网；doctor 只测试本地模型、资料库和空闲 UI，不读取实际游戏画面。安装包是源码包，不含 Python 或虚拟环境；OCR 模型已包含，不会在首次打怪时下载。

## 第一次使用

1. 点击 **设置 → 连接与设置**，选择 MapleStory 窗口。角色可自动读取，也可手填。
2. 点击 **开始新会话**，切回 CW。保持左上角小地图展开，底部经验条与右侧经验提示可见。无需框选或手动校准。
3. 切换浏览器时暂停；切回 CW 自动确认并恢复。移动游戏窗口会跟随位置，改变尺寸会重新适配。暂停和重新确认期间不可见的数据不补猜。
4. 结束时点击 **结束并保存**；CSV 位于 `sessions`。建议首次单人固定地图人工数一小批进行核对。

置顶适用于窗口化与无边框全屏，不保证覆盖独占全屏。拖动原生标题栏移动，拖动边框缩放。请避开小地图、经验条和右侧经验提示；本工具窗口遮挡识别区域时会暂停，移开并切回游戏后恢复。

## 显示与自定义

- **小窗 / 展开**：小窗保留 EXP/小时、状态和开始/结束按钮；展开恢复之前布局与尺寸。
- **设置 → 显示内容**：独立显示地图与角色、升级时间、等级进度、击杀合计和怪物列表。隐藏期间后台统计继续；怪物过多可以拖高窗口或滚动。
- **设置 → 外观**：浅色/深色，雾蓝/松绿/鸢紫，不透明度75%–100%。降低时背景和文字同时透明；设置窗口保持不透明。选项在本机保存。
- **设置 → 识别详情**：查看识别结果；只有主动点击诊断按钮才保存约20秒的提示区及经验条小图，共享8MiB上限。
- **怪物经验表**：内置离线资料或手动覆盖。自动地图识别依赖展开的小地图；倍率应与实际条件一致。

## 数字代表什么

**EXP/小时**：两帧一致且经验/百分比相容的底部经验条增长，除以对应有效观察时间。先累计约30秒；正常可读取时的停手时间包含在平均中，切窗/长期失读暂停计时。

**预计升级**：用当前等级进度推算剩余经验，再按本图本次会话平均速度外推；不是固定倒计时。百分比取整会影响结果。升级、死亡、数字冲突和长缺口会重建基线，不猜跨界增长。换图会建立新地图会话。

**候选击杀**：结合右侧通知、多帧追踪、地图经验表与底部经验条对账。经验条增量等待约6秒配对通知后才可能补计，补回数量标为估计。组队、任务经验、相同经验怪物、快速滚出、遮挡、模糊数字和重叠击杀仍可能造成遗漏或误计。未确定事件数不是未击杀数，也不是误差百分比。

做任务或组队时关闭 **经验条补计（仅单人打怪）**；EXP/小时仍统计实际验证到的经验增长。组队击杀准确性尚未验证。工具不保证精确计数，也不保证任何游戏规则或反作弊结果。

## 数据与隐私

- `settings.json`：本机角色、布局、主题及识别区域；不随源码打包。
- `sessions/`：事件及汇总 CSV，UTF-8 BOM；`diagnostics/`：仅手动启用的诊断；均不上传。
- `assets/`：随源码附带的英文 OCR 模型、字模和社区怪物表。社区表不是官方服务器完整数据。
- `tests/data/`：开发用小块回归样本，不含完整会话录像。
- 普通运行不联网、不发送输入、不读取进程内存、不注入、不读写游戏安装目录。只查询窗口几何并截图可见区域。

## 开发与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts/package_source.py
```

输出 `dist/cw-counter-0.19-source.zip` 和 SHA256。打包使用文件允许列表，排除个人设置、会话、诊断、开发报告、缓存和虚拟环境。资产及第三方来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。GitHub Actions 在 Windows/Python3.12 执行安装、doctor 和回归测试。

验证边界：同机全新解压目录、全新虚拟环境的安装验证可以排除依赖原电脑项目缓存；不能替代另一台不同硬件、分辨率下的真实游戏验证。

本地迁移验证（2026-11-06）：在干净解压目录及全新虚拟环境中，Python 3.12.14 x64、ONNX Runtime 1.23.2、CustomTkinter 5.2.2 安装完成；pip check 无依赖冲突；模型/资料库/空闲 UI 检查通过。145 项回归中141项通过，4项因私人诊断记录未随包提供而跳过。未在第二台物理电脑上验证。
