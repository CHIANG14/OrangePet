# 橘子专注 OrangePet

一只住在 Windows 桌面上的小橘猫：陪你专注、跟着音乐动嘴唱歌，也会在饭点和深夜轻轻提醒你照顾自己。

五种宠物形象均由 Qt 绘制，支持桌面互动和跟唱动画。

## 直接启动

正式打包版本将在 [GitHub Releases](https://github.com/CHIANG14/OrangePet/releases) 发布。下载后将 **`OrangePet.exe`** 放在可写文件夹中，双击启动。使用本仓库的源码时，参照下方的「从源代码运行」。

首次打开会显示小猫和控制面板。关闭面板后，桌面宠物、计时和提醒仍继续运行；需要完全退出时，点击面板右下角“退出”，或右键小猫 / 系统托盘图标选择“退出橘子专注”。

启动器优先打开 `OrangePet.exe`；如果没有打包文件，则尝试使用项目自己的 `.venv`。它不会自动安装依赖或修改全局 Python 环境。

## 和小猫互动

| 操作 | 效果 |
| --- | --- |
| 单击小猫 | 摸摸它，显示温馨回应和爱心 |
| 双击小猫 | 打开番茄钟控制面板 |
| 按住并拖动 | 更换小猫的位置 |
| 右键小猫 | 喂食、播放控制、散步开关、隐藏、退出等 |
| “叫小猫回来” | 把小猫移回主屏幕可见位置 |
| `Ctrl + Alt + O` | 显示 / 隐藏小猫 |
| `Ctrl + Alt + P` | 显示 / 隐藏控制面板 |

在“小猫设置”中可以修改两组全局快捷键。点击对应输入框，按下组合键，再选择“保存快捷键”。组合键须包含 Ctrl 或 Alt，主键支持字母、数字和 F1–F12；不支持 Windows 键或多段快捷键。两个操作不能使用同一组按键。如果按键已被其他程序占用，应用会提示，并尝试保留原来的绑定。

在「小猫设置 → 卡通形象」中可以选择小猫、小青蛙、小奶狗、小兔子或奶蛙。前四只采用圆润的造型，奶蛙保留参考图里的侧瞪眼、扁嘴和松垮站姿。五种形象都支持走路、眨眼、说话、跟唱和庆祝动画。选择立即生效，并随设置保存。

开启散步后，小猫会在屏幕范围内缓缓走动，靠近边缘时转向。拖动、鼠标悬停、专注计时和跟唱期间会暂停散步。

## 番茄钟

- 默认专注 25 分钟、短休息 5 分钟、长休息 15 分钟，可分别设置为 1–180 分钟。
- 每完成 4 轮专注，下一段休息为长休息。
- 支持开始、暂停、继续、重置，以及记录当前想完成的任务。
- 一段计时结束后会等待你开始下一段，不会连续自动推进。
- 每完整完成一轮专注，增加 1 个番茄和 1 份小鱼干。重置和未完成的计时不计入成果。
- 用小鱼干喂猫；新记录初始赠送 3 份。
- 今日完成数量、完整专注分钟数和剩余小鱼干保存在本地。中途退出的计时不恢复，也不会自动计为完成。

修改时长会立即更新尚未开始的对应计时；运行或暂停中的计时保持原时长，下一轮或重置后采用新设置。

## Apple Music 跟唱与播放控制

1. 在 Windows 的 Apple Music 中播放一首歌。
2. 打开“一起听歌”，查看是否识别到了歌曲、歌手和进度。
3. 默认通过 LRCLIB 自动寻找带时间标签的歌词。找到后，小猫头顶会逐句显示歌词，嘴巴跟随播放状态开合。
4. 面板和右键菜单都提供**上一曲、播放 / 暂停、下一曲**操作。暂停后歌曲区不会自动消失；双击歌词区可以把它收起，之后在右键菜单（或托盘菜单）中选择“显示歌词区”即可重新打开。这个开关会随设置保存。

应用优先连接正在播放的 Apple Music 会话；如果 Apple Music 没有在播放，则跟随当前正在播放的系统媒体会话。读取曲目信息和控制播放使用 Windows SMTC 接口，不需要 Apple Music 账号密码，也不会录制声音。

**同步条件与范围：**播放器必须向 Windows 提供媒体会话。Apple Music 的 SMTC 时间轴有时会给出 0 或停滞的进度，应用会用内置时钟平滑估算，让歌词继续逐句滚动；如果播放器完全不提供位置，直接拖到歌曲中段时可能对不上，可用“歌词时间微调”校正。播放器是否接受上下曲等操作也取决于其实现。嘴巴是随播放状态驱动的开合动画，未做音频节拍检测或逐字音素对齐。它不会生成额外的人声。

### 找不到歌词时

可以在播放歌曲后点击“导入 LRC”，选择自己持有的逐句歌词。歌词会关联到当前曲目并缓存在本地。支持 UTF-8、UTF-16、GB18030 编码，以及同一句的多个时间标签。

LRC 格式示例（原创示例文字）：

```text
[ti:橘子的午后]
[ar:原创演示]
[00:00.00]窗边的光，落在小小爪尖
[00:05.00]把今天，过成一颗橘子
[00:10.00]陪你慢慢走，陪你慢慢唱
```

“歌词时间微调”中的**正数让歌词提前，负数让歌词延后**，范围为 ±60 秒。LRC 自带的 `[offset:毫秒]` 也会生效。

不同专辑、现场版、伴奏版的时长和歌词时间轴可能不同。找不到歌词、服务不可达或版本不匹配时，可导入对应版本的本地 LRC，并调整时间偏移。

点击“跟唱演示”可直接查看原创演示歌词和嘴型动画。**演示不播放声音**；演示期间上一曲 / 下一曲用于前后跳转 5 秒，不会操作外部播放器。结束演示后恢复系统音乐联动。

## 问候、温馨提醒与天气

日常陪伴使用**电脑当前本地时间**区分早晨、午间、下午、傍晚、晚间与深夜，包含 98 条问候和鼓励短句：早餐、午饭、晚饭、喝水、伸懒腰、散步、收工和早点休息等。大部分文案为本项目原创，两句古诗标明作者和出处。气泡中的提醒已精简到约 12 个字以内，避免在小猫旁边被截断。

自动提醒可关闭，提醒间隔可以调整。专注和跟唱时减少自动打扰；你也可以手动让小猫说一句。

天气默认城市为**北京**，可在陪伴页面搜索并更换城市。数据来自 Open-Meteo，显示温度、体感、天气状况及当天温度范围，小猫会结合天气给出带伞、添衣或外出散步等提示。不需要 API Key。

天气需要联网，查询的是指定城市对应的坐标，不读取电脑 GPS 或通过 IP 自动定位。天气服务无法连接时，页面会显示状态；其他本地功能仍可使用。天气是城市级参考信息，应以当地实时情况为准。

### 电脑性能监控

在「日常陪伴 → 电脑状态」可查看 CPU 使用率、内存、磁盘和网速，约每 2 秒刷新。配置 LibreHardwareMonitor 后，点击「打开内置温度组件」并保持组件运行，橘子专注约每 30 秒通过 WMI 读取可用的 CPU 和显卡温度。部分传感器需要管理员权限或 PawnIO 驱动。未读到温度时，CPU 使用率、内存、磁盘和网速仍会刷新。[LibreHardwareMonitor 官方说明](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/tree/v0.9.6)

温度组件可选。需要时，从 [LibreHardwareMonitor 官方发布页](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/tag/v0.9.6) 获取便携版，将其解压到应用目录的 `components/LibreHardwareMonitor/`，让该目录直接包含 `LibreHardwareMonitor.exe`。

### 将专注记到任务

在「任务计划」新建任务后，使用「专注时光」的下拉框选择下一轮的关联任务。计时开始后，本轮时长会记到当时选择的任务。上方文本框可留一段自由备注。任务的完成勾选可以撤回。

### 检查更新

从 v1.1.0 开始，在「小猫设置 → 版本与更新」点击「检查更新」。默认仓库为 [CHIANG14/OrangePet](https://github.com/CHIANG14/OrangePet)，也可以填写其他受信任的公开仓库。程序显示最新正式版本和发布说明。确认安装后，程序会校验下载文件的大小和 GitHub 提供的 SHA-256，再退出并启动新版。同目录的 `data` 和 `components` 会继续使用。检查和安装由用户发起。

朋友拿到旧版时，先手动换成已通过启动验证的新版。打包时会读取项目根目录的 `orange-pet-update-repository.txt`，也可以临时指定其他仓库。

```powershell
.\build.ps1 -UpdateRepository 'owner/OrangePet' -SkipInstaller
```

以后发布时，先修改 `orange_pet/__init__.py` 的 `__version__`，再打包。创建同一版本号的公开 GitHub Release，例如代码版本 `1.1.1` 对应标签 `v1.1.1`，把生成的文件作为附件上传，文件名保持 `OrangePet.exe`。草稿和预发布不会进入检查结果。GitHub 需返回附件的 SHA-256。更新渠道仅替换 EXE，温度组件如果有新版，可另行分发 `components`。 [GitHub Releases 文档](https://docs.github.com/en/rest/releases/releases)

每次成功替换会在程序旁保留 `OrangePet.exe.previous`。若新版无法正常运行，退出程序后可将该备份改回原来的 EXE 文件名。若系统拒绝启动新版，更新程序会尝试自动恢复备份。

## 本地数据与联网范围

应用不需要注册账号。程序文件和数据均保留在项目目录，默认使用同目录的 `data/`：

| 路径 | 内容 |
| --- | --- |
| `data/state.json` | 设置、今日成果、累计完成量、星愿瓶、任务、小鱼干和小猫位置 |
| `data/lyrics/` | 按曲目关联的歌词缓存，包括导入的歌词 |
| `data/app.log` | 运行和错误日志，自动轮转 |
| `data/instance.lock` | 同一数据目录的单实例锁 |

自动查找歌词会把歌名、歌手、专辑及可用时长发送到 LRCLIB。天气查询会把你选择的城市名或该城市坐标发送到 Open-Meteo。两项联网功能均可在界面关闭；关闭自动找歌词后仍可使用本地 LRC。

备份个人设置和成果时，退出程序后复制 `data/` 即可。将整个项目移动到其他目录时，一并保留 `data/`。程序检测到无法解析的记录时会先备份为 `state.damaged-*.json`，再开始新记录。

## 从源代码运行

本项目在 **Windows x64、Python 3.14.8、PySide6 Essentials 6.12.0** 环境开发。Windows 系统媒体接口需要 Windows 10 1809 或更新版本；建议在 Windows 11 上使用。

在项目目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

用于检查界面的参数：

```powershell
# 打开无声音的跟唱演示
.\.venv\Scripts\python.exe main.py --demo

# 使用独立测试记录，10 秒后退出
.\.venv\Scripts\python.exe main.py --data-dir .\work\smoke-data --exit-after 10
```

如果需要在其他位置保存记录，可使用 `--data-dir` 指定目录。同一数据目录重复启动会尝试唤出已有面板。

### 测试与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

`build.ps1` 只使用项目 `.venv`，生成根目录下的单文件 `OrangePet.exe`；中间文件写入 `build/`。如果检测到 [Inno Setup 6](https://jrsoftware.org/isdl.php)，会自动编译 `build/installer.iss` 生成带开始菜单、桌面快捷方式和卸载入口的安装程序 `installer_output/OrangePetSetup.exe`，方便分享给朋友。没有 Inno Setup 时直接分发 `OrangePet.exe` 即可。再次打包前先通过应用菜单退出旧实例。脚本不会终止用户进程，不会清理个人数据。

### 主要代码

| 文件 | 作用 |
| --- | --- |
| `main.py` | 程序入口 |
| `orange_pet/app.py` | 控制器、单实例、计时与音乐联动 |
| `orange_pet/pet.py`、`art.py` | 透明桌面窗、鼠标交互、原创矢量猫和动画 |
| `orange_pet/characters.py` | 青蛙、奶狗、兔子等原创矢量卡通形象 |
| `orange_pet/panel.py` | 中文控制面板 |
| `orange_pet/model.py` | 独立计时状态机与本地记录 |
| `orange_pet/music.py`、`lyrics.py` | Windows 媒体会话、播放控制、歌词查询与解析 |
| `orange_pet/hotkeys.py` | Windows 全局快捷键和冲突处理 |
| `orange_pet/care.py` | 分时问候、提醒间隔和文案库 |
| `orange_pet/weather.py` | 城市搜索和 Open-Meteo 天气 |
| `orange_pet/monitor.py` | 系统性能监控（CPU/显卡温度、内存、磁盘、网速） |

## 接口与文案来源

- Windows 媒体会话：[Microsoft SMTC 会话管理器](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager)、[Windows.Media.Control](https://learn.microsoft.com/en-us/uwp/api/windows.media.control)。通过 [PyWinRT](https://pywinrt.readthedocs.io/en/latest/) 调用。
- 自动歌词：[LRCLIB API 文档](https://lrclib.net/docs)。歌词可用性和时间轴取决于其曲库；本项目不内置商业歌曲歌词。
- 天气：[Open-Meteo Forecast API](https://open-meteo.com/en/docs)、[城市搜索 API](https://open-meteo.com/en/docs/geocoding-api)。天气数据由 Open-Meteo 提供，使用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可；地名检索由其 GeoNames 数据提供支持。对外分发或商业使用前，请检查服务当前的使用条件。
- 画面与现代问候语：本项目原创。
- 古诗选句：苏轼[《定风波·莫听穿林打叶声》](https://zh.wikisource.org/zh-hans/%E5%AE%9A%E9%A2%A8%E6%B3%A2_%28%E8%8E%AB%E8%81%BD%E7%A9%BF%E6%9E%97%E6%89%93%E8%91%89%E8%81%B2%29)、[《望江南·春未老》](https://zh.wikisource.org/zh-hans/%E6%9C%9B%E6%B1%9F%E5%8D%97%EF%BC%88%E6%98%A5%E6%9C%AA%E8%80%81%EF%BC%89)。
