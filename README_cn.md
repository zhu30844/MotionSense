# MotionSense

[English](README.md) | 简体中文

最后编辑：2026-10-24

面向 Luckfox Pico Pro Max（Rockchip RV1106）的运动触发录像程序。把 H.264 以 HLS 形式录到 SD 卡上，通过 HTTP 提供实时 MJPEG 流和回放界面，并把运动事件记录到 SQLite。

## 用途

最初是为一台共用冰箱写的——看谁拿了什么。也可能适合其他同类场景：几个小时静止不动，偶尔几秒钟有动静，比如宿舍、储物柜、仓库通道。

- **看完一整天。** 空闲时段压缩回放，什么都不用跳过。
- **全速看那一刻。** 有运动时以高帧率录制和回放。
- **一天的录像不大。** 同一个切换机制就是压住录像体积的原因。
- **看清动静在哪里。** 每次切到高帧率都会在进度条上留下一个标记。

## 截图

实时画面，带 OSD 时间戳和设备状态栏：

![实时画面](docs/img/Screenshot%20From%202026-09-05%2012-52-56.png)

历史记录：有录像的日期日历，按当天的运动量着色：

![运动日历](docs/img/Screenshot%20From%202026-09-05%2012-19-39.png)

回放某一天。进度条上的红色标记是切到高帧率的位置：

![回放](docs/img/Screenshot%20From%202026-09-05%2012-20-03.png)

## 功能

- **自适应帧率。** 空闲时以 1 fps 录制，检测到运动时以 30 fps 录制。阈值、灵敏度和夜间模式均可配置。
- **HLS 录制。** 默认每个关键帧一个 `.ts`，按日期分目录存放，每天一个事件数据库，剩余空间不足时自动清理。
- **实时查看与回放。** `/api/stream` 提供 MJPEG 流，录像按日期浏览；另有 `/api/status` 接口，报告运行时间、内存、负载、SoC 温度和最近一个有录像的日期。
- **OSD 时间戳**，同时叠加在录像和实时流上。

## 整体结构

两个进程，按各自语言擅长的事情划分：

- **`MotionSense`**，C 语言，负责整条流水线——通过 Rockchip 的 rockit 驱动 ISP、编码器和 IVS 运动检测，把 HLS 和元数据数据库写到卡上。它和硬件之间没有任何中间层。
- **`motionsense-agent`**，Go 语言，负责网络——HTTP、界面、API。它从不碰 rockit，所以**没有 cgo**：用 `CGO_ENABLED=0` 构建的静态二进制，通过纯 Go 的 `modernc.org/sqlite` 读取数据库。以 root 运行时监听 80 端口，否则监听 3000。

两者通过 unix socket（`/tmp/motionsense-stream.sock`）通信，这让划分保持干净：守护进程挂掉不会带走 Web 界面，agent 重启也不会打断录像。

配置是 SD 卡上的一个 `config.yaml`，首次启动时从镜像里拷过去，之后不再覆盖。文件缺失时使用编译进程序的默认值，所以一张空卡照样能录。

`S99motionsense` 负责启动两个进程、等待 SD 卡挂载，并从原厂的 `rkipc` 程序手里接管摄像头。它通过板级 overlay 打进镜像，所以刷好的板子第一次开机就开始录像，无需安装、无需配置。

## 要求

- Luckfox Pico Pro Max，SPI NAND 启动
- 一张 **ext4** 格式的 SD 卡。不能带 `orphan_file` 特性——5.10 内核无法以读写方式挂载它，结果什么都起不来。见 [docs/BUILD_cn.md](docs/BUILD_cn.md#sd-卡)。

  FAT32 和 exFAT 能挂载，也能工作——包括 SQLite，因为两者都支持 WAL 所需的共享映射和字节范围锁。不推荐它们，是因为两者都没有日志。这台设备由它所插的东西供电，常常不经关机就被拔掉；ext4 之后会重放日志，FAT 不会，而首当其冲的正是存放一天录像的那个目录。FAT32 另外还把单个文件限制在 4 GB，并且两者都会把每个文件的属主强制为 uid 1000，不管是谁写的。

  规则里也列出了 ntfs、ext2 和 ext3，但这个内核一个都没编进去，所以那些分支永远不会触发。
- 足够存下你想保留的录像的卡。剩余空间低于 `storage.disk_free_min_mb`（默认 2 GB）时，会删除最早的一天来腾地方；录像本身从不停止。
- x86-64 Linux 主机

## 构建

这是 Luckfox SDK 里的一个应用，不是独立项目。它位于该 SDK 一个 fork 的 `project/app/motionsense`，这个 fork 包含板级配置、设备树和开发环境：

**<https://github.com/zhu30844/luckfox-pico-sdk>**

```bash
git clone --recurse-submodules git@github.com:zhu30844/luckfox-pico-sdk.git
cd luckfox-pico-sdk
printf '9\n15\n' | ./build.sh lunch     # hardware "custom" -> MotionSense
./build.sh
adb reboot loader                       # put the board in maskrom/loader mode
./rkflash.sh update
```

### 开发容器

devcontainer 在 **SDK fork** 里，不在本仓库——在 VS Code 里打开的是 `luckfox-pico-sdk`，不是 `MotionSense`。VS Code 会提示 *Reopen in Container*；镜像里带有交叉工具链、Go 和构建依赖，`LF_SDK`、`LF_TOOLCHAIN`、`LF_SYSROOT` 均已设置好。

修改这个应用，就是在那个工作区里修改 `project/app/motionsense`。直接在主机上构建也可以—— `./build.sh` 会自己把工具链加进 `PATH`——前提是装好了 SDK 的构建依赖。

[docs/BUILD_cn.md](docs/BUILD_cn.md) 讲构建链、板级配置、设备上的目录布局，以及起不来时该检查什么。[docs/DEVNOTES_cn.md](docs/DEVNOTES_cn.md) 讲在板子上干活：怎么连上它、链路断了怎么办，以及那些看起来像别的问题的 bug。

## 已知问题

- 在视图之间切换会让客户端计数上涨。超过大约五个客户端后，agent 会有一阵子不响应。
- 运动没有保持窗口：一旦报告一帧静止画面，帧率就回到 1 fps。事件通常不到一秒，所以一个动作的结尾可能以空闲帧率录下来。
- 不支持夏令时。只读取 `/etc/TZ` 中标准时间那一半，所以有夏令时的时区一年中有半年差一小时。

## 计划

- 看门狗。
- 外设。
- 认证。
- OTA。

## 适用范围

一个学习项目。没有按安全产品来构建、测试或审查，也不适合当安全产品用。

具体来说，在本仓库产出的镜像上：

- HTTP 接口没有认证。任何能访问 80 端口的人都能看实时流和全部录像。
- root 密码是厂商的，随镜像发布，从它构建的每块板子都一样。
- SD 卡上的录像和元数据数据库没有加密。
- 没有针对敌意网络做任何加固，这里的东西也都没经过安全审查。

请放在你自己控制的网络里。不要暴露到互联网上，也不要把任何要紧的事情——安全、证据或审计记录——寄托在它身上。

作者对它做了什么或没做到什么不承担任何责任。

## 许可证

MIT——见 [LICENSE](LICENSE)。[docs/THIRD-PARTY_cn.md](docs/THIRD-PARTY_cn.md) 列出了树中所有不受其覆盖的内容。
