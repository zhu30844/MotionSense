# MotionSense

[English](README.md) | 简体中文

最后编辑：2026-11-21

面向 Luckfox Pico Pro Max（Rockchip RV1106，正在适配 Ultra）的运动触发录像程序。把 H.264 以 HLS 形式录到 SD 卡上，通过 HTTP 提供实时 MJPEG 流和回放界面，并把运动事件记录到 SQLite。

## 用途

最初是为一台共用冰箱写的——看谁拿了什么。也可能适合其他同类场景：几个小时静止不动，偶尔几秒钟有运动，比如宿舍、储物柜、仓库通道、地下室。

- **快速看完一整天。** 空闲时段倍速回放，不用拖来拖去。
- **全速看那一刻。** 有运动时以高帧率录制和回放。
- **节约存储空间。** 空闲时每秒只录 1 帧，一天的录像不大。
- **看清动静在哪里。** 每次切到高帧率都会在进度条上留下一个标记。

## 截图

实时画面，带 OSD 时间戳和设备状态栏：

![实时画面](docs/img/Screenshot%20From%202026-09-05%2012-52-56.png)

历史记录：有录像的日期日历，按当天的运动量着色：

![运动日历](docs/img/Screenshot%20From%202026-09-05%2012-19-39.png)

回放某一天。进度条上的红色标记是切到高帧率的位置：

![回放](docs/img/Screenshot%20From%202026-09-05%2012-20-03.png)

## 功能

- **自适应帧率。** 空闲时以 1 fps 录制，检测到运动时以约 30 fps 录制。阈值、灵敏度和夜间模式均可配置。
- **HLS 录制。** 默认每个关键帧一个 `.ts`，按日期分目录存放，每天一个事件数据库，剩余空间不足时自动清理。
- **实时查看与回放。** `/api/stream` 提供 MJPEG 流，录像按日期浏览；另有 `/api/status` 接口，报告运行时间、内存、负载、SoC 温度和最近一个有录像的日期。
- **OSD 时间戳**，同时叠加在录像和实时流上。

## 要求

- Luckfox Pico Pro Max，SPI NAND 启动
- 一张 **ext4** 格式的 SD 卡。不能带 `orphan_file` 特性——5.10 内核无法以读写方式挂载。见 [docs/BUILD_cn.md](docs/BUILD_cn.md#sd-卡)。
- 足够存下你想保留的录像的卡。剩余空间低于 `storage.disk_free_min_mb`（默认 2 GB）时，会删除最早的一天来腾空间；录像本身从不停止。
- x86-64 Linux 主机

## 使用

1. **烧录镜像。** 下载最新的镜像，用完整一键烧录的模式烧录到板载 SPI NAND，而不是 SD 卡。烧录方法见 [安装系统](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Getting-Started/Pico-Pro-Max/)。
2. **格式化 SD 卡为 ext4。** Windows 下可以用 [DiskGenius](https://www.diskgenius.cn/)，Linux 下可以用下面这套命令。

   先运行 `mke2fs -V` 看版本：1.47 及以上照抄即可；低于 1.47（例如 Ubuntu 22.04 自带的 1.46.5）时，去掉下面命令里第 4 步的 `-O ^orphan_file`，否则会报 `Invalid filesystem option set`。旧版本来就不会启用这个特性。

   ```bash
   # 1. 先确认是哪张卡，别选错盘
   lsblk -o NAME,SIZE,MODEL,MOUNTPOINTS

   # 2. 卸载卡上已挂载的分区
   sudo umount /dev/sdX?*

   # 3. 重新分区：MBR 分区表，整张卡一个分区
   sudo parted -s /dev/sdX mklabel msdos mkpart primary ext4 1MiB 100%

   # 4. 格式化成 ext4，不带 orphan_file
   sudo mkfs.ext4 -O ^orphan_file -m 0 -L MOTIONSENSE /dev/sdX1

   # 5. 验证：输出里不应该有 orphan_file
   sudo dumpe2fs -h /dev/sdX1 | grep -i features
   ```

3. **上电。** 插好 SD 卡和摄像头，接上网线，给板子上电。开机后会自动开始录像，无需任何配置。
4. **打开网页。** 在浏览器里打开 `http://<板子的 IP>/`，就能看到实时画面和回放。IP 取决于连接方式：
   - **网线接路由器**：板子通过 DHCP 获取 IP，可以在路由器的设备列表里找到它，也可以用 `adb shell ifconfig eth0` 查看。
   - **USB 线直连电脑**：板子的 USB 网卡固定为 `172.32.0.93`。把电脑上新出现的那块网卡手动设为 `172.32.0.100`，子网掩码 `255.255.0.0`，然后打开 `http://172.32.0.93/`。
   - **网线直连电脑**：没有路由器分配地址，需要手动配置 IP，方法见 Luckfox wiki 的 [离线通信](https://wiki.luckfox.com/zh/Luckfox-Pico-RV1106/Ethernet-Config/#1-%E7%A6%BB%E7%BA%BF%E9%80%9A%E4%BF%A1)。

## 整体结构

两个进程，按各自语言擅长的事情划分：

- **`MotionSense`**，C 语言，负责整条流水线——通过 Rockchip 的 rockit 驱动 ISP、编码器和 IVS 运动检测，把 HLS 和元数据数据库写到卡上。它和硬件之间没有任何中间层。
- **`motionsense-agent`**，Go 语言，负责网络——HTTP、界面、API。它从不碰 rockit，所以**没有 cgo**：用 `CGO_ENABLED=0` 构建的静态二进制，通过纯 Go 的 `modernc.org/sqlite` 读取数据库。以 root 运行时监听 80 端口，否则监听 3000。

两者通过 unix socket（`/tmp/motionsense-stream.sock`）通信，这让划分保持干净：守护进程挂掉不会带走 Web 界面，agent 重启也不会打断录像。

配置是 SD 卡上的一个 `config.yaml`，首次启动时从镜像里拷过去，之后不再覆盖。文件缺失时使用编译进程序的默认值，所以一张空卡照样能录。

正在更改：`S99motionsense` 负责启动两个进程、等待 SD 卡挂载，并从原厂的 `rkipc` 程序手里接管摄像头。它通过板级 overlay 打进镜像，所以刷好的板子第一次开机就开始录像，无需安装、无需配置。

## 构建

这是 Luckfox SDK 里的一个应用，按 Rockchip SDK 的方式集成在 `project/app/motionsense`。下面这个 SDK fork 包含板级配置、设备树和开发环境，记得克隆整个 SDK：

**<https://github.com/zhu30844/luckfox-pico-sdk>**

```bash
git clone --recurse-submodules git@github.com:zhu30844/luckfox-pico-sdk.git
cd luckfox-pico-sdk
./build.sh lunch     # hardware "custom" -> MotionSense_Pro_Max
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

见 [路线图](docs/ROADMAP_cn.md)。

## 适用范围

一个学习项目。没有按安全产品来构建、测试或审查，也不适合当安全产品用。

具体来说，在本仓库产出的镜像上：

- HTTP 接口没有认证，任何能访问 80 端口的人都能看实时流和全部录像。
- root 密码是默认的 `luckfox`。
- SD 卡上的录像和元数据数据库没有加密。
- 没有经过安全审查。

请只在你自己控制的局域网里使用，不要暴露到公网。

作者不承担任何责任。

## 许可证

MIT——见 [LICENSE](LICENSE)。[docs/THIRD-PARTY_cn.md](docs/THIRD-PARTY_cn.md) 列出了树中所有不受其覆盖的内容。
