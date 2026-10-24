# 开发笔记

[English](DEVNOTES.md) | 简体中文

最后编辑：2026-10-24

这块板子上的工作习惯。之所以记录下来，是因为每一条都花了时间才确立。构建和配置细节见 [BUILD_cn.md](BUILD_cn.md)；本文讲的是日常工作的循环。

## 连接

三种同时使用。它们各自独立地失效，这正是同时保留它们的价值所在。

| 链路 | 用途 |
|---|---|
| 以太网 | 预览和 API。速度快，且不受任何干扰 USB 的因素影响。 |
| USB（adb） | 烧录、`adb reboot loader`、推送二进制文件、shell。 |
| 串口（CP210x，115200） | 内核日志，以及在另外两种都失效时仍然可用的 shell。 |

串口控制台不只是用来看日志。当 rootfs 无法读取时，它是唯一剩下的通道：SPI NAND 控制器超时的那次，`/bin/login` 本身都无法执行，ssh 和 adb 都不可用，而控制台仍在输出。

以太网还可以用来再次确认设备是否存活。adb 报告 `offline` 并不代表板子已经宕机——见下文。

## 杀掉守护进程后 adb 变为 offline

在 adb 1.0.41 上反复观察到：执行 `killall -9 MotionSense` 后，USB 重新枚举，主机上的 adb server 保留了一个失效的句柄。`adb devices` 显示 `offline`，而板子仍能正常响应 HTTP。

恢复方法是 `adb kill-server`，或者等待——它经常会自行恢复。

同一次重新枚举会改变 RNDIS 接口的 MAC，因此主机会创建一个*新的* netdev（`enxAAAA` → `enxBBBB`），之前在旧接口上配置的 IPv4 地址随之消失。如果 USB 网络不通，先用 `ip -br addr` 检查接口是否改名，再考虑是不是设备的问题。

## 用 init 脚本停止服务

使用 `/etc/init.d/S99motionsense stop`，而不是 `killall -9`。

`SIGKILL` 不给守护进程释放 ISP 或关闭文件的机会，而且上面每一次 adb 掉线之前都是它。有一次它还打断了一个正在写入的 `adb push`，在设备上留下一个损坏的二进制文件，启动即段错误——而那次 push 报告的是成功。

## 用校验和验证推送

`adb push` 报告成功并不足够。

```bash
adb push project/app/out/bin/motionsense-agent /oem/usr/bin/motionsense-agent
adb shell 'sync; md5sum /oem/usr/bin/motionsense-agent'
md5sum project/app/out/bin/motionsense-agent
```

## 以重启而非服务重启来判断录像

停止再启动服务后，ISP 和 VI 无法恢复采集：守护进程在运行，日期目录和分段目录都已创建，数据库也在写入，但不出现任何 `.ts`。这与录像路径被改坏的表现无法区分。

已用一个与几分钟前还在正常录像的二进制逐字节相同的文件确认过，因此仅重启服务这一项就足以造成该现象。在对录像下任何结论之前，先重启板子。

## 把容器当工具箱

devcontainer 或一个用完即弃的镜像，可以让你用上各种工具而无需安装到主机上。

```bash
# JS syntax check with no node on the host
docker run --rm -v "$PWD/static/js":/js node:20-alpine node --check /js/app.js

# remove build artefacts owned by root
docker run --rm -v "$PWD":/x alpine:latest rm -rf /x/build-output
```

访问 `/dev` 和串口需要 `--privileged -v /dev:/dev`，这就是 SDK 的 devcontainer 声明了它们的原因。在条件允许时，把你的用户加入 `dialout` 是更好的做法——容器的这个标志会把主机上的所有设备都交给容器。

有时容器是唯一可行的途径：`upgrade_tool` 在这台主机上段错误，而在容器里运行正常。同一个二进制，区别在用户空间。

## 值得记住的 bug

下面每一条的表现都与其原因不同。

| 现象 | 原因 | 修复 |
|---|---|---|
| 构建在约 20 分钟后的 app 阶段失败，`output/image` 只生成了一半 | Go 通过运行 git 来写入 VCS 信息，当构建用户不是该检出目录的所有者时，git 会因 `safe.directory` 而失败 | `-buildvcs=false` — `70d750e` |
| `/mnt/sdcard` 始终不挂载，没有守护进程启动，也没有任何提示说明原因 | 卡上的 ext4 带有 `orphan_file`（e2fsprogs 1.47+）；5.10 内核无法以读写方式挂载它，而自动挂载规则要求读写 | `tune2fs -O ^orphan_file` — 见 BUILD_cn.md |
| 重新插拔时卡能被枚举，但启动时不能 | 厂商 dts 设置了 `non-removable`，因此内核核心只扫描一次，从不使用卡检测引脚；这张卡在第一个探测频率下不响应 | dts 中去掉该属性 — `c5aaf49be2`（SDK） |
| 一次会话的第一个 `.ts` 报 `MEDIA_ERR_DECODE` 失败，之后的都能播放 | 编码器不一定首先返回 IDR，而 libhls 会用收到的任何帧开启分段，导致第一个分段没有 SPS/PPS | 丢弃帧直到第一个关键帧 — `ab8af80` |
| 守护进程启动即退出，报 `can't load library 'librockchip_mpp.so.1'`，而该文件存在 | RPATH 能解析守护进程自身的 NEEDED 条目，但解析不了 `librockit.so` 的 | 在 init 脚本中设置 `LD_LIBRARY_PATH` — `aaf319bb67`（SDK） |
| 点击过去的日期返回 500 和 JSON 解析错误 | 当天没有 `EventLogs.db`；`mode=ro` 在文件不存在时失败 | 空的日期返回 200 且无分段 — `dc48835` |
| 画面角标显示“Streaming”，但画面是黑的 | `<img>` 仍持有随守护进程一起断开的连接；`src` 没有变化，因此浏览器认为它已加载 | 用新的查询字符串重新请求 — `74beb6d` |
| 每次启动一两分钟后时钟快了八小时，而 RTC 始终正确 | rkipc 自带 NTP 客户端（`[network.ntp] enable = 1`，60 s），会把时区加到收到的 UTC 上，再让 busybox 把结果当作 UTC 写回。S99 中的 `RkLunch-stop.sh` 无法阻止它：RkLunch 通过一个在后台运行、先等待 /userdata 的 `post_chk` 启动 rkipc，因此 stop 调用在该进程存在之前就已执行 | 在 oem hook 中移除 rkipc 及其 ini 文件 — `529f3537f6`（SDK） |
| 在本地午夜到 08:00 之间，状态卡片把昨天显示为最后一次录像，而今天的分段就在卡上 | Go 读取 TZ 和 /etc/localtime，从不读取 /etc/TZ，而镜像中没有 zoneinfo，因此 time.Local 为 UTC，而守护进程用本地时间命名目录。于是今天的目录在排序上超前于 Go 认为的“今天”，被防未来日期的检查丢弃 | agent 将 /etc/TZ 解析为 time.Local — `8a2ee60` |
| 刚烧录、插着空白卡的板子显示“Failed to load motion data”，连接被直接断开而不是得到响应 | agent 在启动时以 mode=ro 打开 VideoMetadata.db，文件不存在时失败；守护进程只在第一个分段时才创建它，由此产生的 nil *Storage 传到了处理函数中并被解引用 | 首次使用时再连接，文件不存在时返回空日历 — `dceebcc` |

## 未解之谜

有一次会话结束时，SPI NAND 和 SD 控制器同时超时：

```
rockchip-sfc ffac0000.spi: wait sfc idle timeout
ubi0 error: ubi_io_read: error -5 while reading 188 bytes from PEB 413
dwmmc_rockchip ffaa0000.mmc: DTO timeout when already completed
mmc1: tried to HW reset card, got error -110
```

agent 由于已经常驻内存，仍在继续响应。断电重启后问题消失，下一次启动没有出现存储错误。在此之前的会话中，曾对一个正在写卡的守护进程反复执行 `killall -9`，但这只是相关性，不是诊断。记录在此，以防再次出现。

---

由 Claude（Opus 5）在这块板子上工作时撰写。由 ZIXUAN ZHU 审阅。
