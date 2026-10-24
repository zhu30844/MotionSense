# 构建与安装 MotionSense

[English](BUILD.md) | 简体中文

最后编辑：2026-10-24

MotionSense 的目标硬件是 Luckfox Pico Pro Max（Rockchip RV1106，SPI NAND）。它作为 Luckfox SDK 内的一个应用进行构建，位于该 SDK 一个 fork 中的 `project/app/motionsense`：

- SDK fork：<https://github.com/zhu30844/luckfox-pico-sdk>
- 本仓库是它的一个 submodule。

构建产物有两个：C 守护进程 `MotionSense`，以及 `agent/` 下的 Go HTTP UI/API `motionsense-agent`。两者都安装到 `/oem/usr/bin`，并由同一个 init 脚本启动。

---

## 快速开始

```bash
git clone --recurse-submodules git@github.com:zhu30844/luckfox-pico-sdk.git
cd luckfox-pico-sdk
printf '9\n15\n' | ./build.sh lunch     # hardware "custom" -> MotionSense
./build.sh                              # ~20 min cold, minutes warm

adb reboot loader                       # put the board in maskrom/loader mode
./rkflash.sh update
```

`upgrade_tool` 在某些主机上会段错误，而在 devcontainer 内运行正常，所以如果 `./rkflash.sh` 崩溃，就在 devcontainer 内烧录。`rkflash.sh` 的单分区目标（`boot`、`rootfs` 等）不会先上传 loader，会以 "parameter is invalid" 失败；`update` 才是可用的路径。

镜像为 `output/image/update.img`，另有一份带时间戳的副本位于 `IMAGE/IPC_SPI_NAND_BUILDROOT_RV1106_MOTIONSENSE_<date>_RELEASE_TEST/`。

submodule 嵌套两层——本应用在 SDK 之下，media-server 在本应用之下——因此 `--recurse-submodules` 不可省略。对已有的检出：`git submodule update --init --recursive`。

SDK fork 中提供了一个 devcontainer（`.devcontainer/`），其中已配置好工具链、Go 以及 `LF_*` 环境变量。在主机上构建同样可行；`./build.sh` 会自行把交叉工具链加入 `PATH`。

---

## 构建链

`./build.sh` 运行 SDK 的常规流水线。MotionSense 在 app 阶段进入其中：

`./build.sh` 先运行 `build_all`，再运行 `build_save`：

```
build_all
  ├─ build_sysdrv    u-boot, kernel, buildroot   -> output/out/{sysdrv_out,rootfs_uclibc_rv1106}
  ├─ build_media     Rockchip media libraries    -> output/out/media_out
  ├─ build_app       project/app/Makefile        -> output/out/app_out
  └─ build_firmware  staging, images, update.img -> output/image
build_save                                       -> IMAGE/<name>_<date>_RELEASE_TEST
```

添加本应用无需修改 SDK 中的任何内容：`project/app/Makefile` 会发现任何包含 `Makefile` 的子目录。

```
build_app
  └─ $(wildcard ./*/Makefile) finds motionsense/Makefile
       ├─ c-daemon: cmake configure + build + install -> install-sdk/
       │            MAROC_COPY_PKG_TO_APP_OUTPUT      -> project/app/out/{bin,share}
       └─ go-agent: go build                          -> project/app/out/bin/
     project/app/out -> output/out/app_out
```

### build_firmware

分区镜像在这一步组装。顺序很重要，因为每一步都为下一步提供输入：

```
build_env                    partition table + sys_bootargs   -> env.img
build_meta                   fastboot builds only             -> meta.img
__PACKAGE_ROOTFS             sysdrv rootfs tarball, then overlays
                             app_out/root, media_out/root, external/
                             + the generated /etc/init.d mount script
__PACKAGE_OEM                app_out and media_out {bin,lib,share,usr,etc}
                             -> oem staging, plus its init.d script
__RUN_PRE_BUILD_OEM_SCRIPT   RK_PRE_BUILD_OEM_SCRIPT
                             (preceded by __RUN_POST_CLEAN_FILES, which drops
                             the NPU/AIISP/audio models the board did not select)
build_mkimg <oem>            -> oem.img            (RK_BUILD_APP_TO_OEM_PARTITION=y)
__RUN_POST_BUILD_SCRIPT      RK_POST_BUILD_SCRIPT
post_overlay                 RK_POST_OVERLAY, rsync'd over the rootfs staging
build_mkimg <rootfs>         -> rootfs.img
__PACKAGE_USERDATA           media_out/install_to_userdata, app_out/install_to_userdata
__RUN_POST_BUILD_USERDATA_SCRIPT   reads RK_PRE_BUILD_USERDATA_SCRIPT
build_mkimg userdata         -> userdata.img
build_tftp_sd_update
build_updateimg              -> update.img
```

在这一序列中会运行四个板级配置 hook，它们都相对于板级配置自身所在目录解析：

| 变量 | 时机 | 本开发板 |
|---|---|---|
| `RK_PRE_BUILD_OEM_SCRIPT` | oem staging 填充完成之后、`oem.img` 之前 | `motionsense-oem-pre.sh` |
| `RK_POST_BUILD_SCRIPT` | `oem.img` 之后、overlay 之前 | 未设置 |
| `RK_POST_OVERLAY` | 在此之后，覆盖到 rootfs staging 上 | `overlay-luckfox-config`、`-buildroot-init`、`-buildroot-shadow`、`overlay-motionsense` |
| `RK_PRE_BUILD_USERDATA_SCRIPT` | userdata staging 之后、`userdata.img` 之前 | `luckfox-userdata-pre.sh` |

oem hook 是从镜像中剔除文件的位置：它在所有内容复制进 staging 目录之后、文件系统生成之前，对该目录运行。`motionsense-oem-pre.sh` 用它删除 media 构建安装的 demo 和测试二进制文件。

注意 vendor 的命名：函数名是 `__RUN_POST_BUILD_USERDATA_SCRIPT`，但它读取的变量是 `RK_PRE_BUILD_USERDATA_SCRIPT`。

`build_mkimg` 根据 `RK_PARTITION_FS_TYPE_CFG` 选择文件系统，根据 `RK_PARTITION_CMD_IN_ENV` 确定大小。对 ubifs，它调用 `sysdrv/tools/pc/mtd-utils/mkfs_ubi.sh`，后者构建三个变体（page/block 为 2KB/128KB、2KB/256KB、4KB/256KB），并将与默认几何参数匹配的那个符号链接为 `<name>.img`。

### Luckfox 在 Rockchip SDK 之上添加的内容

hook 与 overlay 机制来自 Rockchip；填充这些机制的脚本来自 Luckfox，全部位于 `project/cfg/BoardConfig_IPC/`。

| 脚本 | Hook | 使用者 |
|---|---|---|
| `luckfox-buildroot-oem-pre.sh` | `RK_PRE_BUILD_OEM_SCRIPT` | 11 个板级配置 |
| `luckfox-buildroot-nocsi-oem-pre.sh` | 同上 | 2 个（无摄像头的开发板） |
| `luckfox-glibc-oem-pre.sh` | 同上 | 目前无 |
| `luckfox-userdata-pre.sh` | `RK_PRE_BUILD_USERDATA_SCRIPT` | 14 个板级配置 |
| `luckfox-rv1106-tb-spi_nand-post.sh` | `RK_POST_BUILD_SCRIPT` | SPI NAND fastboot 配置 |
| `luckfox-rv1106-tb-emmc-post.sh` | 同上 | eMMC fastboot 配置 |
| `luckfox-systemd-off-modem-post.sh` | 同上 | 目前无 |

各 `*-oem-pre.sh` 脚本结构相同：一个 `lf_rm` 辅助函数，加一个从 `$RK_PROJECT_PACKAGE_OEM_DIR` 中删除内容的 `remove_data()`——删除 AIISP 模型、`libdrm`、`libkms`、`libfreetype`、`libiconv`、`librkAVS`、`libjpeg`、`libpng` 以及 vqe 数据文件。`motionsense-oem-pre.sh` 就是该文件再加上本开发板自己的删除项。

`luckfox-userdata-pre.sh` 从 userdata staging 中删除 `*.sh` 和 `*.bmp`。

fastboot 的 `*-post.sh` 脚本更大：它们把 `usr/ko` 裁剪到快速启动所需的模块，并按保留列表精简 oem 目录树。

overlay 位于同一目录下的 `overlay/`：

| Overlay | 安装内容 |
|---|---|
| `overlay-luckfox-config` | `usr/bin/luckfox-config` 和两个 init 脚本：`S99luckfoxconfigload`（启动时运行 `luckfox-config load`）和 `S99luckfoxcustomoverlay` |
| `overlay-luckfox-buildroot-init` | `S50sshd`、`S60micinit`、`S99hciinit`、`S99python`、`S99rtcinit`、`S99usb0config`、`etc/profile`、`usr/bin/iomux` |
| `overlay-luckfox-buildroot-shadow` | `etc/shadow`、`etc/ssh/sshd_config`、`etc/samba/{smb.conf,smbpasswd}` |
| `overlay-luckfox-wifibt-firmware` | rtl8723b 固件 blob |
| `overlay-luckfox-fastboot`、`-buildroot-tiny` | 为快速启动精简的 `etc/inittab`、`etc/fstab` |
| `-buildroot-86panel`、`-rgb`、`-webbee`、`-sim7600g`、`-ppp`、`-glibc-*` | 其他 Luckfox 开发板 |

本开发板使用前三个。

需要了解的是 `S99usb0config`：当 USB 控制器处于 peripheral 模式时，它把 `usb0` 设为 `172.32.0.93`，最多重试十次。RNDIS 地址就来自这里。

Luckfox 还在 `build.sh` 本身中添加了：`LF_*` 板级配置变量（`LF_TARGET_ROOTFS`、`LF_BOOT_MEDIA`、`LF_HARDWARE`、`LF_SYSTEM`、`LF_ORIGIN_BOARD_CONFIG`、`LF_WIFI_SSID`/`LF_WIFI_PSK`、`LF_ENABLE_SPI_NAND_FAST_BOOT`），由这些数组生成的 `lunch` 菜单，以及为 SD 卡启动介质打包 `sd_update.img` 的 `lf_blkenvpackage`。

这里的 `Makefile` 是一个薄封装。它 include `../Makefile.param` 以获得交叉工具链和 media 路径，然后驱动与独立构建流程相同的 CMake 构建。若把它复制到别处，有两个细节会出问题：

- `CURRENT_DIR` 必须在 `include ../Makefile.param` *之前* 求值；后者会引入 `.BoardConfig.mk`，否则 `$(lastword $(MAKEFILE_LIST))` 会指向它。
- 必须设置 `SHELL := /bin/bash`。`Makefile.param` 的复制和 strip 宏使用 `[[ ]]`，而 GNU make 不会把 `SHELL` 传递给子 make。

### 构建并行度

Buildroot 会把自己串行化。除非每个 package 都有独立的 target 和 host 目录，否则其 Makefile 会声明 `.NOTPARALLEL`，于是无论主机有多少核，package 都严格逐个构建；板级配置开启了这种隔离：

```
BR2_PER_PACKAGE_DIRECTORIES=y
```

切换此项会改变输出布局，因此 buildroot 必须从空目录树开始构建。`./build.sh clean rootfs` 不够——它会保留 `output/{build,host,staging,target}`，随后第一个 package 会在 rsync 中以 `mkdir .../per-package/<pkg>/target failed` 失败。在更改后的首次构建之前，需手动删除 `sysdrv/source/buildroot/buildroot-2023.02.6/output` 及其 `.config`。按 buildroot 自己的说法，该功能也仍属实验性质：一个暗中依赖了某个从未声明为依赖项的 package，今天能构建成功，在隔离下则会失败。

job 数来自 `RK_JOBS`，默认是主机核数的四分之三。用 `LF_JOBS` 覆盖，而不是 `RK_JOBS`——`build.sh` 顶部的 `unset_env_config_rk` 会清空环境中找到的每个 `RK_*`，因此调用方传入的 `RK_JOBS` 在应用默认值之前就已经没了：

```bash
LF_JOBS=$(nproc) ./build.sh rootfs
```

调高它意义不大。在一台 24 核主机上测量，从空 output 目录构建 rootfs，ccache 已预热：

| jobs | 耗时 |
|---|---|
| 12 | 148 s |
| 18（默认） | 146 s |
| 24 | 144 s |
| 32 | 144 s |

整个范围内相差四秒。负载峰值约为 7-13，远未接近核数，因为限制这次构建的是依赖图以及每个 package 的串行部分——configure、install、per-package rsync——而不是并行槽位的数量。想在构建期间让机器保持可用时才设置 `LF_JOBS`，而不是为了让构建更快。

`BR2_JLEVEL` 并不是它看上去那样的开关。当 `MAKEFLAGS` 已带有 `-j` 时，Buildroot 会省略自己的 `-j`，而 `sysdrv/Makefile` 总是传入 `-j$(SYSDRV_JOBS)`，因此 package 的子 make 从该 jobserver 获得并行度——`.NOTPARALLEL` 只串行化声明它的那个 make，不影响递归调用的 make。`BR2_JLEVEL` 仍然控制的是在 buildroot 目录树内手动运行的裸 `make`，这正是调试单个 package 的方式；vendor 基线将其固定为 4，fragment 将其设为 0（每个 CPU 一个 job，再加一）。

### 仅构建本应用

```bash
cd project/app/motionsense
make            # both binaries, staged into project/app/out
make c-daemon   # C only
make go-agent   # Go only
make clean
make info       # prints the resolved toolchain / media / output paths
```

`go-agent` 依赖 `c-daemon` 纯粹是为了排序：`Makefile.param` 设置了 `MAKEFLAGS += -j`，没有这个依赖，两者会产生竞争，`MAROC_STRIP_DEBUG_SYMBOL` 可能会处理到一个写了一半的 agent 二进制文件。

之后在 SDK 根目录运行 `./build.sh firmware` 重新打包镜像。

### 独立构建（不生成镜像，仅二进制文件）

```bash
cd project/app/motionsense
cmake -S . -B build && cmake --build build -j
```

工具链按以下顺序解析：显式的 `-DCMAKE_C_COMPILER`（SDK 构建会传入），然后是 `$LF_TOOLCHAIN`，再然后是相对于本目录树在 SDK 中位置的 `../../../tools/linux/toolchain/...`。工具链已不再 vendor 在本仓库中。

独立构建还需要 `vendor/`，它不在仓库中——见下文 *Rockchip 库*。用以下命令填充一次：

```bash
./scripts/sync-vendor.sh            # or: ./scripts/sync-vendor.sh <sdk-path>
```

### Go agent

```
GOOS=linux GOARCH=arm GOARM=7 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w"
```

不需要 CGO：`modernc.org/sqlite` 是纯 Go 实现，因此二进制文件是静态的，不链接 uclibc。`-s -w -trimpath` 把它从 15.7MB 缩小到 11MB。

Makefile 在 `MAROC_STRIP_DEBUG_SYMBOL` 之后构建 agent，使 Go 二进制文件不经过这一步；该步骤运行的是 GNU `strip`。

必须加 `-buildvcs=false`。否则 Go 会运行 git 把 commit 写入二进制文件，并在用户不拥有该检出目录时让构建失败，这包括以 root 身份 `docker run` 以及大多数 CI：

```
fatal: detected dubious ownership in repository at '.../project/app/motionsense'
error obtaining VCS status: exit status 128
```

`agent/` 没有 `vendor/` 目录，因此冷构建会下载模块，需要网络访问。

agent 监听 `:5000`，提供通过 `go:embed` 嵌入的 Web 资源，并通过 `/tmp/motionsense.sock` 从 C 守护进程读取帧。它容许先于 C 守护进程启动：数据库缺失时会记录日志并跳过，socket 读取端会重试。

### 通过 adb 推送到运行中的开发板

`deploy.sh` 构建并推送二进制文件，无需重新烧录。它不推送任何库，因此设备上必须已有这些库。在改用 buildroot 提供的库之前构建的镜像中没有 `libsqlite3.so.0` 或 `libyaml-0.so.2`，守护进程将无法启动。在这类设备上烧录一次 `update.img`，之后 `deploy.sh` 即可使用。

---

## 依赖来源

| 依赖 | 来源 | 所在位置 |
|---|---|---|
| `librockit`、`librkaiq`、`librockchip_mpp`、`librga` | `output/out/media_out`（SDK 构建） | `/oem/usr/lib` |
| `libsqlite3`、`libyaml`、`libfreetype`、`libiconv` | buildroot sysroot | `/usr/lib`（rootfs） |
| `libhls`/`libmpeg`（`3rdparty/media-server`，submodule）、`libosd`（`3rdparty/osd`） | 从源码构建，静态 | 链接进二进制 |

### Rockchip 库

由 `MS_RK_MEDIA_DIR` 选择：设置时——SDK 的 `Makefile` 会设置——应用针对 `output/out/media_out` 构建，跟随 SDK 刚刚构建出的内容。未设置时，回退到 `vendor/`。

`vendor/` 不在仓库中。`scripts/sync-vendor.sh` 会创建它，从 SDK 检出中提取库和头文件。它读取 `media/`，SDK 在那里以源码形式提供这些内容，因此一个普通的 SDK 克隆就足够，无需构建 SDK。

只有独立构建需要它。SDK 的应用构建读取 `output/out/media_out`。

该脚本复制四个 `.so` 文件及其头文件。它不复制 `.a` 归档或 `librockit_full/tiny.so`；没有任何东西链接它们。

四个发行版库来自 `cmake/SystemLibs.cmake`，它从 buildroot sysroot 导入这些库，使用与 vendor 副本相同的 CMake target 名称（`sqlite3::sqlite3`、`yaml::yaml`、`freetype::freetype`、`iconv::iconv`）。

### media-server

`3rdparty/media-server` 是 ireader/media-server 的 submodule，固定在 `ea53ac6`，保持原样不改。只编译 `libmpeg` 和 `libhls`；该项目的其余部分（flv、mov、mkv、dash、rtsp 等）不使用。构建胶水代码由我们编写，位于 `cmake/MediaServer.cmake`，因为 submodule 无法携带本地文件。

有一个文件没有原样使用。`hls_media_input()` 对 DTS 连续性的断言方式不允许 `duration == 0`——即"每个关键帧切一个分段"，这正是 `storage.c` 所用的方式，也是 `config.yaml` 出厂时的 `hls_duration_s: 0`。打过补丁的副本位于 `3rdparty/media-server-local`，`cmake/MediaServer.cmake` 用它代替 submodule 中的文件进行编译，因此 submodule 永远不会显示为 dirty。版本升级后如何刷新它，见该目录下的 README。Release 构建定义了 `NDEBUG`，会把该断言编译掉，因此这只影响 `-DCMAKE_BUILD_TYPE=Debug` 构建，后者在录制一开始就会 abort。

升级固定版本时，应匹配 `libmpeg/source`、`libmpeg/include` 和 `libhls/include` 的 tree hash，而不是单个文件。只匹配 `hls-media.c` 会选中 `8928fa5`，即这个很少改动的文件在上游的最新修订；在那个版本中，其余 48 个文件里有 20 个不同，生成的二进制文件小 8KB。在 `ea53ac6`，49 个被编译文件中有 48 个与之前 vendor 的副本逐字节相同。

本应用需要哪些 buildroot package，声明在 `buildroot-packages.fragment` 中，放在应用里，而不是放在远离需要它的代码的某个 SDK 文件中。SDK 把 `RK_BUILDROOT_DEFCONFIG` 作为 make target 直接传给 buildroot，因此 buildroot 需要一个完整的 defconfig，且没有接入任何 fragment 机制；fragment 通过以下命令应用：

```bash
./scripts/gen-buildroot-defconfig.sh
```

它从 `luckfox_pico_defconfig` 加上声明的 package 重新生成 `sysdrv/tools/board/buildroot/motionsense_defconfig`，并刷新已解压的 buildroot 目录树中的副本。编辑 fragment 后运行它，然后重新构建。它是单独的步骤而不是构建 hook，因为 defconfig 在 SDK 的 sysdrv 阶段就被使用，早于本应用能注册的任何 hook。

本应用不打包任何共享库。它所需的一切都已在镜像中，因此只要设置了 `MS_RK_MEDIA_DIR`，就会跳过 Rockchip `.so` 文件的 `install()`。

---

## 设备端布局

```
/oem/usr/bin/MotionSense                     the C daemon
/oem/usr/bin/motionsense-agent               the Go HTTP UI/API, port 5000
/oem/usr/share/MotionSense/fonts/            OSD font
/oem/usr/share/MotionSense/config.yaml       seed copy
/oem/usr/lib/                                Rockchip media libraries
/etc/init.d/S99motionsense                   start script (from the board overlay)
/mnt/sdcard/MotionSense/                     log, live config
/mnt/sdcard/MotionSense/agent.log            agent log
/mnt/sdcard/DCIM/                            recordings
```

二进制文件以 `RPATH=$ORIGIN/../lib` 链接，从 `/oem/usr/bin` 解析为 `/oem/usr/lib`。这覆盖了守护进程自身的 `NEEDED` 条目，但不覆盖传递依赖：`librockit.so` 需要 `librockchip_mpp.so.1` 和 `librga.so`，而解析某个库的依赖时不会参考可执行文件的 RPATH。因此 `S99motionsense` 导出 `LD_LIBRARY_PATH=/oem/usr/lib`。没有它，守护进程会在 exec 时以 `can't load library 'librockchip_mpp.so.1'` 退出。

### 时区

镜像中没有 zoneinfo 数据库，因此命名时区无法解析。`overlay-motionsense/etc/TZ` 存放一个 POSIX 时区字符串，uclibc 会直接读取：

```
AWST-8
```

符号与名称给人的印象相反：`AWST-8` 表示 UTC+8。它和该目录下的其他内容一样经由 `RK_POST_OVERLAY` 进入镜像，因此打包时无需额外步骤。

没有它，设备运行在 UTC 上，OSD 时间戳和录制开始时间——两者都调用 `localtime()`——都会偏差相应的时差。

时钟本身在启动时来自 RTC，之后来自 ntpd。RTC 电池耗尽时冷启动，第一个分段会以 ntpd 校正之前时钟里的任意日期记录。

`S99motionsense` 启动前会等待 `/mnt/sdcard` 挂载（最多 30s），并先从原厂 `rkipc` 应用接管摄像头。SD 卡由 rootfs 中附带的 udev 规则（`sysdrv/tools/board/eudev/rules/61-sd-cards-auto-mount.rules`）自动挂载，支持 vfat/exfat/ntfs/ext2/3/4。

两个进程通过 `CFG_SOCKET_PATH`（`/tmp/motionsense-stream.sock`）通信，该 socket 由 C 守护进程创建，agent 连接它获取 MJPEG 帧。它只在 `config.h` 中定义一次；两端都读取这个名称。录制不经过它，因此 socket 故障只会损失实时画面，不影响其他功能。

正常启动的情况如下：

```
$ /etc/init.d/S99motionsense status
MotionSense: running
agent: running
$ grep sdcard /proc/mounts
/dev/mmcblk1p1 /mnt/sdcard ext4 rw,noatime 0 0
$ tail -1 /mnt/sdcard/MotionSense/agent.log
[stream] connected to /tmp/motionsense-stream.sock
$ ls /mnt/sdcard/DCIM/$(date +%F)/00001/
00000.ts  00001.ts  index.m3u8
```

### SD 卡

**文件系统不得使用 `orphan_file`。** e2fsprogs 1.47 及更高版本默认启用它。它占用 ext4 ro_compat 第 16 位，而这个 5.10 内核不支持该特性，因此卡会以只读方式挂载，而要求读写挂载的自动挂载规则会失败。`/mnt/sdcard` 永远不会出现，`S99motionsense` 超时退出，两个守护进程都不会启动。要清除该特性，在 PC 上执行：

```bash
sudo e2fsck -f /dev/sdX1
sudo tune2fs -O ^orphan_file /dev/sdX1
```

**卡可能需要重试才能完成枚举。** 在本开发板上，它并不总是在第一个探测频率下响应：

```
mmc_host mmc1: Bus speed (slot 0) = 400000Hz
mmc1: error -110 whilst initialising SD card
mmc_host mmc1: Bus speed (slot 0) = 300000Hz
mmc1: new high speed SDXC card at address 59b4
```

因此 `rv1106g-motionsense.dts` 去掉了 vendor 的 `non-removable`。设置该属性时，内核核心只在 probe 时扫描一次，忽略卡检测引脚且从不重试，使启动时的失败成为永久性的；重新插拔卡也不会产生任何事件。

总线速度上限为 SD High Speed，50MHz——`no-1-8-v` 排除了需要 1.8V 信号的 UHS 模式。在一张 119GiB SDXC 卡上测得：

| | |
|---|---|
| 顺序读 | 22.1 MB/s |
| 顺序写 | 19.0 MB/s |
| 4K 随机读 | 中位数 0.70 ms |
| 4K 同步写 | 中位数 9.4 ms，p95 15 ms，最差 32 ms |

以几 Mbps 录制只占用带宽的一小部分。如果元数据数据库以 `PRAGMA synchronous=FULL` 提交，则同步写延迟适用。

### 仅重新烧录应用

应用位于独立分区，因此迭代时无需完整重新烧录：

```bash
./rkflash.sh oem
```

`rkflash.sh` 还接受 `boot`、`rootfs`、`userdata`、`uboot`、`loader`、`update`、`erase`。

通过 adb 推送二进制文件并重启服务还要更快。

**判断录制是否正常要以完整重启为准，而不是服务重启。** 停止再启动 S99motionsense 后，ISP 和 VI 无法恢复采集：守护进程在运行，日期和分段目录被创建，数据库被写入，但不产生任何 `.ts`。重启即可恢复。已用一个与此前刚刚还在正常录制的二进制文件逐字节相同的二进制文件确认。

---

## 板级配置

产品专用配置位于 SDK fork 中的独立目录，不改动上游 Luckfox 文件：

```
project/cfg/BoardConfig_MotionSense/
├── BoardConfig-SPI_NAND-Buildroot-RV1106_MotionSense-IPC.mk
├── motionsense-oem-pre.sh                    oem trimming for this board only
├── luckfox-userdata-pre.sh          -> symlink into BoardConfig_IPC/
└── overlay/
    ├── overlay-luckfox-config       -> symlink
    ├── overlay-luckfox-buildroot-init   -> symlink
    ├── overlay-luckfox-buildroot-shadow -> symlink
    └── overlay-motionsense/etc/init.d/S99motionsense

sysdrv/source/kernel/arch/arm/boot/dts/rv1106g-motionsense.dts
sysdrv/tools/board/buildroot/motionsense_defconfig
```

这些符号链接不可或缺。`post_overlay()` 和 pre-build hook 相对于板级配置自身所在目录解析名称，且 `post_overlay()` 用 `[ -d ]` 做判断，会静默跳过缺失的 overlay。没有这些链接，构建仍会成功，但镜像中会缺少 vendor 的 init 脚本。

该板级配置不在 `./build.sh lunch` 的编号菜单中——那个列表硬编码在 `build.sh` 里。通过最后一项 `custom` 选择它，该项列出所有匹配 `BoardConfig_*/BoardConfig*.mk` 的文件。如果增删板级配置，索引（上文中的 15）会变化。

### 分区

```
256K(env) 256K(idblock) 512K(uboot) 4M(boot) 60M(oem) 10M(userdata) 180M(rootfs)
```

占用 256MB SPI NAND 中的 255MB。最近的占用情况：

| 分区 | 大小 | 已用 |
|---|---|---|
| boot | 4 MB | 3.55 MB |
| oem | 60 MB | 9.75 MB |
| userdata | 10 MB | 1.88 MB |
| rootfs | 180 MB | 52.00 MB |

没有任何环节会根据分区大小校验镜像。超大的镜像可以正常构建和烧录而不报任何错误，然后在启动时失败。`boot` 余量最小，为 11%；添加内核驱动后要检查它。

### 设备树

`rv1106g-motionsense.dts` include vendor 的 `rv1106-luckfox-pico-pro-max-ipc.dtsi`，只覆盖不同之处，因此从不修改 vendor dts。添加 `.dts` 无需修改 Makefile：内核通过通用的 `%.dtb` 模式规则，经 `make <name>.img` 构建它，而 vendor 的 luckfox dts 文件也都没有在 `arch/arm/boot/dts/Makefile` 中注册。

它还修正了 vendor dts 的问题：其中 sdmmc 节点把属性拼写成 `max-freqency`；该拼写会被忽略，控制器从 `rv1106.dtsi` 继承 `max-frequency = <200000000>`。

---

## 无法迁出的上游改动

产品改动位于上述目录中。有八个 vendor 文件带有无法迁到那里的修改，因为它们是读取构建开关的地方，而不是声明开关的地方。与上游同步时需要手动合并：

| 文件 | 原因 |
|---|---|
| `media/luckfox/Makefile` | 读取 `RK_ENABLE_LUCKFOX_TEST` |
| `media/sysutils/Makefile` | 读取 `RK_ENABLE_SYSUTILS_TESTS` |
| `media/ive/ive/CMakeLists.txt`、`media/rga/Makefile`、`media/rockit/rockit/mpi/CMakeLists.txt` | 读取 `RK_ENABLE_SAMPLE` 等 |
| `media/cfg/cfg.mk` | `CONFIG_RK_ISP_BUILD_DEMO=n`，是一个值而不是开关 |
| `sysdrv/Makefile` | 传入 `BR2_CCACHE_DIR`；复制 `*_defconfig`，使开发板可以携带自己的 defconfig |
| `sysdrv/tools/board/buildroot/luckfox_pico_defconfig` | `BR2_DL_DIR` |

**关闭**一个 package 不只是把它列出来。追加在基础 defconfig 之后的 `# BR2_X is not set` 行会被当作注释，不起任何作用，因此 `gen-buildroot-defconfig.sh` 改为从基础文件中删除启用该 package 的那一行。

Buildroot 也从不移除已取消选择的 package 之前安装的内容。`output/target/` 是增量构建的，因此这些文件会保留下来并被打包进 `rootfs.tar`，尽管该 package 已不再构建——取消选择 ntp 后，镜像中仍留有 `/usr/sbin/ntpd` 和 `/etc/init.d/S49ntp`。在已有目录树上，强制重建 target：

```bash
cd sysdrv/source/buildroot/buildroot-2023.02.6 && make target-finalize && make
```

全新的检出不会遇到这个问题：该 package 根本不会被构建。

`sysdrv/Makefile` 中的 defconfig 复制只在 buildroot 尚未解压时运行。在已有目录树上修改 `motionsense_defconfig` 后，需要手动复制进去；否则构建会使用过时的版本：

```bash
cp sysdrv/tools/board/buildroot/*_defconfig \
   sysdrv/source/buildroot/buildroot-2023.02.6/configs/
```

---

## 已验证

用本目录树构建的完整镜像已烧录到 Pico Pro Max 上并运行：开发板以 `rv1106g-motionsense.dts` 启动，SD 卡以读写方式自动挂载，两个守护进程自动启动，ISP 以 2304x1296 初始化传感器，HLS 分段和按天生成的 `EventLogs.db` 写入 `DCIM`，agent 连接到帧 socket，`/api/stream` 以每帧 44.7KB 提供 15.0 fps。

## 许可

`../LICENSE` 为 MIT，覆盖此处编写的代码。`THIRD-PARTY.md` 划定了与其他所有内容的边界：Rockchip OSD 源码（3-clause BSD）、DejaVu 字体、Video.js（Apache-2.0）、media-server（MIT，submodule），以及 Rockchip media 库——这些库被引用但不随本项目分发。

---

由 Claude（Opus 5）根据 SDK 源码及在 Luckfox Pico Pro Max 上的测试编写。由 ZIXUAN ZHU 审阅。
