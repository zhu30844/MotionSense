# 构建与安装 MotionSense

[English](BUILD.md) | 简体中文

最后编辑：2026-11-27

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

`upgrade_tool` 在某些主机上会段错误，而在 devcontainer 内运行正常，所以如果 `./rkflash.sh` 崩溃，就在 devcontainer 内烧录。打不开板子时它同样会段错误：Maskrom 模式下的 USB 节点是 `root:root` 0664，除非主机上有 udev 规则，所以 devcontainer 里的 `dev` 在 `root` 组里。`rkflash.sh` 的单分区目标（`boot`、`rootfs` 等）不会先上传 loader，会以 "parameter is invalid" 失败；`update` 才是可用的路径。

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
| `RK_POST_BUILD_SCRIPT` | `oem.img` 之后、overlay 之前 | `motionsense-rootfs-post.sh` |
| `RK_POST_OVERLAY` | 在此之后，覆盖到 rootfs staging 上 | `overlay-motionsense` |
| `RK_PRE_BUILD_USERDATA_SCRIPT` | userdata staging 之后、`userdata.img` 之前 | 未设置 |

oem hook 是从镜像中剔除文件的位置：它在所有内容复制进 staging 目录之后、文件系统生成之前，对该目录运行。`motionsense-oem-pre.sh` 用它删除 media 构建安装的 demo 和测试二进制文件。

`motionsense-rootfs-post.sh` 对 rootfs staging 做同样的事，处理 buildroot 选项去不掉的东西：libv4l 工具里的几个 compliance 工具，以及 `ssh-keyscan`。它还让 dhcpcd 不去管 `usb0`，因为这个接口的地址是固定的。

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

Pro Max 的镜像一个都不用。`luckfox-config` 在启动时重新分配排针引脚，而底板的引脚已固定在设备树里。其余的大多在这个镜像里什么都不做（没有 Python、`amixer`、`hciattach` 和 samba 可供它们操作），`S99rtcinit` 则会在发现 RTC 未设置时往里写 2024-01-01。仍然需要的部分现在是 MotionSense 自己的，由它的 `Makefile` 安装：

| 原来 | 现在 |
|---|---|
| `S99usb0config` 给 `usb0` 设 `172.32.0.93` | `S51usbaddr` 里的一行 |
| `S50sshd` 里对 `/var/empty` 的 `chown` | `S49sshdir`；`S50sshd` 用 buildroot 自带的 |
| 带 `PermitRootLogin yes` 的 `etc/ssh/sshd_config` | 本仓库里的 `sshd_config` |
| 带 root 密码的 `etc/shadow` | `buildroot-packages.fragment` 里的 `BR2_TARGET_GENERIC_ROOT_PASSWD` |
| `etc/profile` | buildroot 自带的 |

`./build.sh firmware` 不会清空暂存目录 `output/out/rootfs_uclibc_rv1106`，所以某个 overlay 被去掉后，它的文件仍会留在镜像里，直到 `./build.sh rootfs` 把这个目录重新解包一遍。

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

独立构建还需要 `vendor/` 下的 Rockchip 库，它们不在仓库中——见下文 *Rockchip 库*。用以下命令填充一次：

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

仓库根目录下的 `ms` 收纳了日常命令。不带参数运行会列出全部：

```
./ms status     what is running, safe mode, boot count, storage, clock
./ms logs       follow the system log, the agent's and the vendor libraries'
./ms deploy     build both programs and the web pages, push them, restart
./ms time       set the board's clock and RTC from this machine
./ms sim        the simulator and the web dev server together
```

在主机上或 devcontainer 里都能用：在主机上启动时，它会把自己转到容器里去执行。adb 只在容器里使用，因为板子归先启动的那个 adb 服务端所有，主机上的服务端会让容器里的看不到板子。如果找不到板子，在主机上执行 `adb kill-server`。

`ms deploy` 不推送任何库，因此设备上必须已有这些库。在改用 buildroot 提供的库之前构建的镜像中没有 `libsqlite3.so.0` 或 `libcjson.so.1`，守护进程将无法启动。在这类设备上烧录一次 `update.img`，之后 `ms deploy` 即可使用。

---

## 依赖来源

| 依赖 | 来源 | 所在位置 |
|---|---|---|
| `librockit`、`librkaiq`、`librockchip_mpp`、`librga` | `output/out/media_out`（SDK 构建） | `/oem/usr/lib` |
| `libsqlite3`、`libcjson`、`libfreetype`、`libiconv` | buildroot sysroot | `/usr/lib`（rootfs） |
| `libhls`/`libmpeg`（`3rdparty/media-server`，submodule）、`libosd`（`3rdparty/osd`） | 从源码构建，静态 | 链接进二进制 |

### Rockchip 库

由 `MS_RK_MEDIA_DIR` 选择：设置时——SDK 的 `Makefile` 会设置——应用针对 `output/out/media_out` 构建，跟随 SDK 刚刚构建出的内容。未设置时，回退到 `vendor/`。

`vendor/` 下的 Rockchip 库不在仓库中。`scripts/sync-vendor.sh` 会把它们拷入，从 SDK 检出中提取库和头文件。它读取 `media/`，SDK 在那里以源码形式提供这些内容，因此一个普通的 SDK 克隆就足够，无需构建 SDK。

只有独立构建需要它。SDK 的应用构建读取 `output/out/media_out`。

该脚本复制四个 `.so` 文件及其头文件。它不复制 `.a` 归档或 `librockit_full/tiny.so`；没有任何东西链接它们。

发行版库来自 `cmake/SystemLibs.cmake`，它从 buildroot sysroot 导入这些库，使用与 vendor 副本相同的 CMake target 名称（`sqlite3::sqlite3`、`freetype::freetype`、`iconv::iconv`），另有 `cjson::cjson`。

### media-server

`3rdparty/media-server` 是 ireader/media-server 的 submodule，固定在 `ea53ac6`，保持原样不改。只编译 `libmpeg` 和 `libhls`；该项目的其余部分（flv、mov、mkv、dash、rtsp 等）不使用。构建胶水代码由我们编写，位于 `cmake/MediaServer.cmake`，因为 submodule 无法携带本地文件。

有一个文件没有原样使用。`hls_media_input()` 对 DTS 连续性的断言方式不允许 `duration == 0`——即"每个关键帧切一个分段"，这正是 `storage.c` 所用的方式，也是 `hls_duration_s` 默认值 0 所选的方式。打过补丁的副本位于 `3rdparty/media-server-local`，`cmake/MediaServer.cmake` 用它代替 submodule 中的文件进行编译，因此 submodule 永远不会显示为 dirty。版本升级后如何刷新它，见该目录下的 README。Release 构建定义了 `NDEBUG`，会把该断言编译掉，因此这只影响 `-DCMAKE_BUILD_TYPE=Debug` 构建，后者在录制一开始就会 abort。

升级固定版本时，应匹配 `libmpeg/source`、`libmpeg/include` 和 `libhls/include` 的 tree hash，而不是单个文件。只匹配 `hls-media.c` 会选中 `8928fa5`，即这个很少改动的文件在上游的最新修订；在那个版本中，其余 48 个文件里有 20 个不同，生成的二进制文件小 8KB。在 `ea53ac6`，49 个被编译文件中有 48 个与之前 vendor 的副本逐字节相同。

本应用需要哪些 buildroot package，声明在 `buildroot-packages.fragment` 中，放在应用里，而不是放在远离需要它的代码的某个 SDK 文件中。SDK 把 `RK_BUILDROOT_DEFCONFIG` 作为 make target 直接传给 buildroot，因此 buildroot 需要一个完整的 defconfig，且没有接入任何 fragment 机制；fragment 通过以下命令应用：

```bash
./scripts/gen-buildroot-defconfig.sh
```

它从 `luckfox_pico_defconfig` 加上声明的 package 重新生成 `sysdrv/tools/board/buildroot/motionsense_defconfig`，并刷新已解压的 buildroot 目录树中的副本。编辑 fragment 后运行它，然后重新构建。它是单独的步骤而不是构建 hook，因为 defconfig 在 SDK 的 sysdrv 阶段就被使用，早于本应用能注册的任何 hook。

fragment 里有两项不是 package。一项指向 `busybox.fragment`，buildroot 把它叠在厂商的 busybox 配置上，它关掉 telnet 的客户端和服务端（登录走 ssh），以及 `inetd`、`dnsd`、`crond`、`tftp` 和 `wget`。另一项是 root 的密码，写成 MD5 哈希：工具链的 uClibc 编译时没有带 SHA-256 的 `crypt()`，而 buildroot 对明文密码用的正是这种哈希，sshd 会拒绝这样的密码。要去掉 busybox 装过的东西，buildroot 必须从空的 `output` 重新构建，原因见上文 per-package 目录一节。

本应用不打包任何共享库。它所需的一切都已在镜像中，因此只要设置了 `MS_RK_MEDIA_DIR`，就会跳过 Rockchip `.so` 文件的 `install()`。

---

## 设备端布局

```
/oem/usr/bin/MotionSense                     the C daemon
/oem/usr/bin/motionsense-agent               the Go HTTP UI/API, port 5000
/oem/usr/bin/ms-update                       starts an update (see Updates)
/oem/usr/share/MotionSense/fonts/            OSD font
/oem/usr/lib/                                Rockchip media libraries
/etc/init.d/S99motionsense                   start script (installed by the app build)
/etc/motionsense/board.json                  board file (from the board overlay)
/userdata/update/                            update package, its result and log
/mnt/sdcard/MotionSense/config.json          configuration
/mnt/sdcard/MotionSense/motionsense.log      stderr of the vendor libraries
/mnt/sdcard/MotionSense/agent.log            agent log
/mnt/sdcard/DCIM/                            recordings
```

字体按相对于二进制文件的位置（`../share/MotionSense/fonts/`）查找，不用绝对路径。

启动脚本就是应用自己的 `S99motionsense`，每块板子都相同。应用构建把它放在输出目录的 `root/` 下，`build.sh` 在盖 overlay 之前把它拷进 rootfs；overlay 里如果还带着一份，会把它替换掉。

### 板级文件

`/etc/motionsense/board.json` 声明这块板子有什么。两个程序都读它；`MS_BOARD_FILE` 可以指定另一个文件，`scripts/pcsim.sh` 就是这样在 PC 上运行它们的。

```json
{
  "name": "luckfox-pico-pro-max",
  "storage": {
    "root": "/mnt/sdcard",
    "removable": true
  }
}
```

| 键 | 含义 | 缺失时 |
|---|---|---|
| `name` | 这是哪块板子。升级包里写的必须是同一个名字。 | 不接受任何升级包 |
| `storage.root` | 录像、配置和日志的存放位置。`DCIM/` 和 `MotionSense/` 建在它下面。 | `/mnt/sdcard` |
| `storage.removable` | 根目录是一个可能不存在的挂载点。挂载之前不写任何东西。 | `true` |

文件不存在等同于空文件。这个文件属于镜像，放在板子的 `overlay-motionsense` 里，不属于应用：应用在每块板子上都相同。

### 配置

存储上 `MotionSense/` 目录里的 `config.json` 存放用户可以改的内容。文件不存在时守护进程按默认值写出一份，启动时读取一次。缺失的键取默认值。类型不对的值会被忽略，并在日志里留一条警告；文件不是合法 JSON 时保持原样不动，使用默认值。

| 键 | 默认值 | 含义 |
|---|---|---|
| `record.width`、`record.height` | 1920、1080 | 录制分辨率 |
| `record.fps` | 30 | 录制流的传感器帧率 |
| `record.bitrate_kbps` | 4000 | |
| `record.gop` | 60 | 关键帧间隔，单位为帧 |
| `live.width`、`live.height` | 1920、1080 | 实时画面分辨率 |
| `live.fps` | 30 | 与 `record.fps` 相等时保留传感器给出的每一帧；设为一半则隔一帧取一帧 |
| `live.bitrate_kbps` | 2000 | |
| `live.gop` | 30 | 关键帧间隔，单位为帧；新观看者要等到一个关键帧 |
| `ivs.width`、`ivs.height` | 640、360 | 运动检测所用的分辨率 |
| `ivs.fps` | 15 | |
| `ivs.md_interval` | 4 | 每 N 帧分析一次 |
| `ivs.md_sensibility` | 3 | 检测灵敏度，1 到 5 |
| `ivs.md_night_mode` | true | |
| `ivs.thresh_sad`、`ivs.thresh_move` | 40、2 | 检测阈值 |
| `ivs.area_ratio` | 0.05 | 画面中有多大比例在动才算运动 |
| `ivs.poll_ms` | 100 | 轮询检测结果的间隔 |
| `ivs.fps_low`、`ivs.fps_high` | 1、30 | 无运动和有运动时的录制帧率 |
| `ivs.motion_debounce_ms` | 1000 | 运动日志的采样间隔 |
| `osd.font_size`、`osd.margin` | 36、16 | 像素 |
| `osd.position` | `bottom-right` | `top-left`、`top-right`、`bottom-left` 或 `bottom-right` |
| `storage.hls_duration_s` | 0 | 0 表示每个关键帧切一个分段；大于 0 时还要求攒够这么多秒 |
| `storage.disk_free_min_mb` | 2048 | 剩余空间低于此值时删除最旧的日期 |
| `storage.cleanup_every_ts` | 20 | 每隔多少个分段检查一次剩余空间 |

二进制文件以 `RPATH=$ORIGIN/../lib` 链接，从 `/oem/usr/bin` 解析为 `/oem/usr/lib`。这覆盖了守护进程自身的 `NEEDED` 条目，但不覆盖传递依赖：`librockit.so` 需要 `librockchip_mpp.so.1` 和 `librga.so`，而解析某个库的依赖时不会参考可执行文件的 RPATH。因此 `S99motionsense` 导出 `LD_LIBRARY_PATH=/oem/usr/lib`。没有它，守护进程会在 exec 时以 `can't load library 'librockchip_mpp.so.1'` 退出。

### 时区

镜像中没有 zoneinfo 数据库，因此命名时区无法解析。`overlay-motionsense/etc/TZ` 存放一个 POSIX 时区字符串，uclibc 会直接读取：

```
AWST-8
```

符号与名称给人的印象相反：`AWST-8` 表示 UTC+8。它和该目录下的其他内容一样经由 `RK_POST_OVERLAY` 进入镜像，因此打包时无需额外步骤。

没有它，设备运行在 UTC 上，OSD 时间戳和录制开始时间——两者都调用 `localtime()`——都会偏差相应的时差。

时钟本身在启动时来自 RTC，之后来自 ntpd。RTC 电池耗尽时冷启动，第一个分段会以 ntpd 校正之前时钟里的任意日期记录。

SDK 的 `S21appinit` 在开机时执行 `/oem/usr/bin/RkLunch.sh`，这个名字由各个应用用自己的启动逻辑来填。我们的这份通过调用厂商的 `insmod_ko.sh` 加载摄像头的内核模块，别的什么都不做。原先占着这个位置的是厂商的 `rkipc` 应用的脚本，它现在不再被构建：`project/app` 下的每个应用只在板级配置的 `RK_APP_TYPE` 里有它认识的名字时才构建，我们的名字是 `MOTIONSENSE`。这个变量留空会让所有应用都不构建，包括我们的。

有两个目录会留着以前的构建放进去的东西，所以应用不再安装的文件仍然会被打包：各应用安装到的 `project/app/out`，以及拼装 oem 分区的 `output/out/oem`。改了 `RK_APP_TYPE`，或者从安装清单里去掉了某个文件之后，构建前要执行 `./build.sh clean app` 并删掉 `output/out/oem`。漏掉后者，曾让一个不含 rkipc 的镜像里仍然带着 rkipc 的 `RkLunch-stop.sh`、一个字体和两个库。CI 是从空目录构建的，不受影响。

`S99motionsense` 启动两个程序。两个程序各自等待存储，等多久都行：之后守护进程创建 `MotionSense/`，在没有配置时写出 `config.json`，并把 vendor 库的 stderr 接到 `motionsense.log`。SD 卡由 rootfs 中附带的 udev 规则（`sysdrv/tools/board/eudev/rules/61-sd-cards-auto-mount.rules`）自动挂载，支持 vfat/exfat/ntfs/ext2/3/4。

两个进程通过 `CFG_SOCKET_PATH`（`/tmp/motionsense-stream.sock`）通信，该 socket 由 C 守护进程创建，agent 连接它获取实时画面的 H264 帧。它只在 `config.h` 中定义一次；两端都读取这个名称。录制不经过它，因此 socket 故障只会损失实时画面，不影响其他功能。

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

### 进程监管

一共三层，每一层处理上一层看不到的故障。

**程序退出后会被重新启动。** `S99motionsense start` 为每个程序起一个循环，也就是脚本自己带 `supervise` 参数运行，程序退出两秒后把它重新拉起。`stop` 先结束循环，再由循环停掉它管的程序，所以升级期间不会有东西被拉起来。`status` 报告的是这两个循环。

**程序卡死会让板子复位。** 守护进程在采集和编码起来之后打开 `/dev/watchdog`，只有写盘线程持续存下帧时才喂它，所以进程卡死、采集停住、存储卡写入阻塞的结果都一样：约 45 秒后复位。正常停止会解除看门狗；还在等卡的板子没有打开它。agent 不碰看门狗：页面卡住不是复位整机的理由。设备节点来自板级设备树里的 `&wdt`。

**一直失败的板子会停止尝试。** 连续五次启动后一分钟内就退出，循环会重启板子。每次开机给 `/userdata/motionsense/boot_count` 加一，守护进程连续运行五分钟后清零。开机时发现它超过五，就只启动 agent、不启动守护进程，并把它清零，这样板子仍然可以访问，下次断电重启会再试一次。此时 `status` 会提示，并且存在 `/tmp/motionsense-safe-mode`。

这些数值在 `S99motionsense` 开头和 `config.h`（`CFG_WATCHDOG_TIMEOUT_S`）里。

### SD 卡

**文件系统不得使用 `orphan_file`。** e2fsprogs 1.47 及更高版本默认启用它。它占用 ext4 ro_compat 第 16 位，而这个 5.10 内核不支持该特性，因此卡会以只读方式挂载，而要求读写挂载的自动挂载规则会失败。`/mnt/sdcard` 永远不会出现，守护进程一直等待存储而不录制。要清除该特性，在 PC 上执行：

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

因此 `rv1106g-motionsense-pro-max.dts` 去掉了 vendor 的 `non-removable`。设置该属性时，内核核心只在 probe 时扫描一次，忽略卡检测引脚且从不重试，使启动时的失败成为永久性的；重新插拔卡也不会产生任何事件。

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

通过 adb 推送二进制文件并重启服务还要更快。推送前先停止服务：只是杀掉程序的话，它会在文件还没写完时被重新拉起。

---

## 板级配置

产品专用配置位于 SDK fork 中的独立目录，不改动上游 Luckfox 文件：

```
project/cfg/BoardConfig_MotionSense_Pro_Max/
├── BoardConfig-SPI_NAND-Buildroot-RV1106_MotionSense_Pro_Max-IPC.mk
├── motionsense-oem-pre.sh                    oem trimming for this board only
├── motionsense-rootfs-post.sh                rootfs trimming for this board only
└── overlay/
    └── overlay-motionsense/etc/
        ├── motionsense/board.json
        ├── hostname, hosts, issue            the board's name
        └── TZ

sysdrv/source/kernel/arch/arm/boot/dts/rv1106g-motionsense-pro-max.dts
sysdrv/tools/board/buildroot/motionsense_defconfig
```

这些符号链接不可或缺。`post_overlay()` 和 pre-build hook 相对于板级配置自身所在目录解析名称，且 `post_overlay()` 用 `[ -d ]` 做判断，会静默跳过缺失的 overlay。没有这些链接，构建仍会成功，但镜像中会缺少 vendor 的 init 脚本。

该板级配置不在 `./build.sh lunch` 的编号菜单中——那个列表硬编码在 `build.sh` 里。通过最后一项 `custom` 选择它，该项列出所有匹配 `BoardConfig_*/BoardConfig*.mk` 的文件。如果增删板级配置，索引（上文中的 15）会变化。

### 分区

```
256K(env) 256K(idblock) 512K(uboot) 512K(misc) 8M(recovery) 6M(boot) 48M(rootfs) 65024K(oem) 512K(vnvm) 130560K(userdata)
```

占用 256MB SPI NAND 中的 255MB。板子上实测：

| 分区 | 大小 | 可用 | 已用 |
|---|---|---|---|
| recovery | 8 MB | 8 MB | 4.02 MB |
| boot | 6 MB | 6 MB | 3.55 MB |
| rootfs | 48 MB | 36.3 MB | 18.9 MB |
| oem | 63.5 MB | 50.1 MB | 15.3 MB |
| userdata | 127.5 MB | 107.4 MB | 0.03 MB |

一个 UBI 分区有 12 到 20 MB 被坏块预留和文件系统自身占掉，分区越大占得越多。

没有任何环节会根据分区大小校验镜像。超大的镜像可以正常构建和烧录而不报任何错误，然后在启动时失败。

**这个布局是为通过 recovery 升级准备的**，不做 A/B；见下面的*升级*一节。改分区表意味着重刷，而 2.0 本来就要求重刷一次。

| 分区 | 原因 |
|---|---|
| misc | 存放让下次启动进入 recovery 的标记 |
| recovery | 一个内核加一个 busybox 小系统，负责刷写升级包 |
| boot | 6 MB 而不是 4 MB：屏幕驱动会让内核变大 |
| rootfs | 现在用量的两倍；只有 buildroot 的包会装到这里 |
| oem | 应用，以及给屏幕进程、字体和模型留的空间 |
| vnvm | 瑞芯微的 vendor 存储：只属于这一块板子的东西，比如它的以太网地址 |
| userdata | 剩下的全部：存放升级包 |

顺序是有讲究的。`misc`、`recovery`、`vnvm` 和 `userdata` 永远不能挪：前两个挪了 U-Boot 就找不到，第三个里是无法重新生成的东西，升级包在第四个里面。`boot`、`rootfs` 和 `oem` 夹在它们中间，所以以后的升级可以写入新的分区表，让这三个互相调整大小。现在还没有做这件事。

`vnvm` 是 U-Boot 和内核要找的名字，换个名字就找不到。它有四个擦除块，是格式所需的两倍，用来应对坏块。构建不为它生成镜像，所以升级包和整机重刷都不会写它：实测过，U-Boot 第一次启动时存进去的地址，在用同一个镜像再刷一遍之后仍然在。用烧录工具擦除整片 flash 则会把它清掉。构建时会为它打印一行红色的 "Not found image file"，那是打包脚本跳过了它，不是失败。

#### 以太网地址

它存在 `vnvm` 里，是第 3 项：十二个字节，也就是两个地址。板子只有一个以太网口 `eth0`，第一个地址是它的。第二个之所以存在，是因为瑞芯微的格式给两个网口留了位置，而 U-Boot 两个都会校验：发现第二个是空的，它会随机补一个并把这一项重写一遍，我们的脚本随后发现这一项变了又写回去，如此每次启动都重复。这是从 U-Boot 的代码读出来的，没有实际试过。所以第二个填的是一个固定的值，也就是为 `eth1` 这个名字算出来的地址，这块板子上没有任何东西用它。

每次启动有三处会碰这一项，顺序如下：

1. **U-Boot** 读出它，把第一个地址交给内核。读不到时它随机生成一个并存进去。
2. **内核** 使用 U-Boot 交给它的地址。
3. **`RkLunch.sh`** 算出地址应该是什么，如果 vendor 存储里是另一个、而且是它可以替换的，就把算出来的写进去，并立刻设到 `eth0` 上。

算出来的地址是 `motionsense eth0 <序列号>` 的 SHA-256 的前六个字节，序列号是芯片的，取自 `/proc/cpuinfo`。首字节的最低位清零、次低位置一：这是单播、本地管理的地址，也就是没有花钱买号段的地址应有的形式。它每次启动都一样，整片 flash 被擦掉之后也一样。只有空白板子的第一次启动会先用另一个地址，也就是 `RkLunch.sh` 还没运行时 U-Boot 随机生成的那个。

`RkLunch.sh` 可以替换什么：

| vendor 存储里是什么 | 结果 |
|---|---|
| 什么都没有 | U-Boot 存入一个随机地址，随后被替换 |
| 带本地管理位的地址，即第二个十六进制数字是 2、3、6、7、a、b、e 或 f | 被算出来的地址替换 |
| 不带这一位的地址 | 保持不动：它被当作工厂写入的地址 |
| 第 200 项的内容是 `01` | 保持不动，不管地址是什么 |

单靠这一位分不出随机的地址和有人选定的地址，而手工选定的地址本来就应该带这一位。第 200 项就是说明"这些地址是选定的"的标记。瑞芯微自己的项只到 17，所以 200 归我们用。它和地址放在一起，地址到哪它就到哪。

`ms-vendor` 用来在 shell 里读写 vendor 存储。要给一块板子指定自己的地址，把两个地址和标记都写进去，然后重启：

```sh
ms-vendor set 3 0a00000000010e0000000001    # eth0，然后是没有用到的第二个地址
ms-vendor set 200 01
```

`ms-vendor set 200 00` 会让板子在下次启动时换回算出来的地址。`ms-vendor get 3` 打印现在存的内容。

在 Pro Max 上试过，序列号 `b6e432ffe46093d3`，算出来的地址是 `86:e2:85:8d:2e:d2`：第一次启动它就在 `eth0` 上，从第二次启动起由 U-Boot 给出；手工写入的 `00:11:22:33:44:55` 重启后仍在；手工写入的 `0a:00:00:00:00:01` 在没有标记时被替换，有标记时两次重启都保留，清掉标记后被替换。没有接网线试过，所以没有从路由器那一侧确认。

#### USB 网络的地址

USB 网络有两个地址：板子这一端的 `usb0`，以及板子告诉电脑、让电脑那一端使用的地址。内核每次创建 gadget 时都把两者随机生成一遍，也就是每次启动。电脑按地址给网卡命名并记住它，所以在电脑看来，板子每次启动都是一块新网卡，之前为上一块配置的东西，比如固定 IP，就没了。

`ms-hwaddr <名字>` 打印为某个名字算出来的地址，算法和以太网地址相同：`ms-hwaddr usb0` 和 `ms-hwaddr usb0-host` 就是这两个，`ms-hwaddr eth0` 则是 `RkLunch.sh` 用的那个。

`S51usbaddr` 负责设置它们。它紧跟在厂商的 `S50usbdevice` 之后运行，后者负责建立 gadget，而且没有留出可以做这件事的位置。内核只在没有任何配置使用这个功能时才接受地址，所以脚本先把 gadget 从总线上摘下来，写入地址，再放回去：电脑会看到板子离开又回来一次，间隔约 0.4 秒，发生在启动后 5 秒左右。这两个地址不存进 vendor 存储：在这个脚本之前没有任何东西要读它们，重新算一遍也不花什么。

同一个脚本还给 `usb0` 设 IP 地址：`172.32.0.93`，子网掩码 `255.255.0.0`，也就是 README 让用户访问的那个。

在 Pro Max 上试过：两次启动之后 `usb0` 都是 `0a:76:7c:90:8b:3a`，电脑上的网卡都是 `enx1a43fd60638f`；按厂商脚本在拔线时的做法重启 gadget 之后也一样。在此之前，电脑上的网卡每次启动都换一个名字。只用 Linux 电脑试过。

`userdata` 的大小保证最大的升级包放得下：`boot`、`rootfs`、`oem` 全部装满时约 93 MB，可用空间是 107 MB。

### 升级

运行中的板子用升级包升级，由 recovery 小系统刷写。不能回到旧版本：新版本可能已经改了数据库，退回去就得让旧版本读得懂它。旧系统唯一的用处是把断电中断的升级刷完，而 recovery 用每个分区一份就能做到。

升级包是一个普通的 tar，由 `scripts/mk-update.sh` 从完成的构建里打出（`scripts/mk-release.sh` 会在发布包旁边打一个）：

| 成员 | 内容 |
|---|---|
| `manifest` | `board=` 和 `version=` 两行 |
| `SHA256SUMS` | 每个镜像一行 |
| `recovery.img`、`boot.img`、`rootfs.img`、`oem.img` | 默认四个都带，47 MB；`--only oem` 只打应用 |

永远不带 `uboot`：写它的时候断电，板子就完全起不来了。永远不带 `userdata`：配置和升级包本身都在里面。

升级包也带 `recovery.img`，除非用 `--only` 把它排除。recovery 不能重写自己，所以由 `ms-update` 在主系统里处理它，在设置任何标记之前：先读出分区的内容，只有和镜像不同才写入并回读校验。所以大多数升级不会动它。写入期间断电没有代价：板子照常启动。这种情况下会留下一个文件 `/userdata/update/recovery-pending`，只要它还在，不带 `recovery.img` 的升级包就会被拒绝：标记加上损坏的 recovery 会让板子无处可启动。任何带着它的升级包（每个发布包都带）都会把分区修好并继续升级。

一次升级的过程：

1. 用 `PUT /api/update` 上传升级包。agent 把它存成 `/userdata/update/incoming.tar`，然后运行 `ms-update`。
2. `update/ms-update` 检查板子有 `misc` 和 `recovery`、manifest 写的是这块板子（板级文件里的 `name`）、每个成员都是那四个镜像之一、校验和正确。然后把包移成 `update.tar`，把失败启动计数清零，在 `misc` 的 16 KB 偏移处写上 `boot-recovery`，板子重启。被它拒绝的包会被删掉，原因返回给调用方。
3. U-Boot 看到标记，启动 `recovery` 而不是 `boot`。
4. `update/recovery.sh` 在擦除任何东西之前再检查一遍升级包，然后逐个分区擦、写，镜像从 tar 里直接流出来。它在 `/userdata/update/result` 里留一行（`ok: boot rootfs oem` 或 `failed: ...`），旁边留一份日志，最后才清掉标记并重启。
5. `S99motionsense` 在开机时删掉 `/userdata/update` 里残留的升级包。

中途断电时标记还在，所以下次开机仍进 recovery，从头再刷一遍。写入失败会重试三次；断电不算一次。

LED 显示 recovery 进行到哪里：写入时快闪，成功后慢闪五秒，失败后长亮五秒。

agent 从不删除文件。删掉被拒绝或只传了一半的升级包是 `ms-update` 的事（后者用 `--discard`），开机清理是启动脚本的事。

recovery 脚本通过 `RK_RECOVERY_LUNCH_SCRIPT` 进入镜像，这是加在 `build.sh` 里的一个钩子：板级配置指定自己目录下的一个文件，这里是指向 `update/recovery.sh` 的符号链接。`RK_MISC` 设为 `blank-misc.img`，即空标记；不设置时默认是 `recovery-misc.img`，它会让第一次启动就进入 recovery 并带上 `--wipe_all`。

在板子上试过的：

- 通过接口完成一次完整升级；事先放在 `rootfs` 和 `oem` 里的文件升级后都没有了。
- 别的板子的包、带 `uboot.img` 的包、校验和不对的包、没有 manifest 的包都被拒绝，shell 和接口各试过。
- 接受之后才损坏的包：recovery 报告损坏，旧系统原样启动。
- 写 `rootfs` 时拔掉电源：恢复供电后从头重刷并完成。
- 带有改动过的 `recovery.img` 的升级包：分区回读的内容是新镜像，新的 recovery 随后刷入了其余分区。没有改动时分区原样不动。
- 擦掉 `recovery` 并留下 `recovery-pending`，相当于写它时断电：板子正常启动，拒绝了不带 `recovery.img` 的升级包，默认的升级包把它修好并完成了升级。

没有覆盖的：

- **任何能访问 agent 的人都能给板子刷固件。** 没有认证，升级包也没有签名。在 agent 有登录之前，这只适用于可信的网络。
- 写入失败和三次重试从来没有发生过：没有办法让好的 flash 写失败。
- 写进去的内容不回读，只检查升级包。
- 完整刷完却仍然起不来的新系统需要通过 USB 重刷。
- 只支持 NAND。Ultra 是 eMMC：它的分区表需要 `misc` 和 `recovery`，脚本需要一个写块设备的分支，它还需要自己的板级文件。现在它和 Pro Max 共用一份，连名字也是。
- 还没有页面。`/api/status` 里的 `version` 能看出升级是否成功；结果文件和日志是留给 adb 查看的。

### 设备树

`rv1106g-motionsense-pro-max.dts` include vendor 的 `rv1106-luckfox-pico-pro-max-ipc.dtsi`，只覆盖不同之处，因此从不修改 vendor dts。添加 `.dts` 无需修改 Makefile：内核通过通用的 `%.dtb` 模式规则，经 `make <name>.img` 构建它，而 vendor 的 luckfox dts 文件也都没有在 `arch/arm/boot/dts/Makefile` 中注册。

它还修正了 vendor dts 的问题：其中 sdmmc 节点把属性拼写成 `max-freqency`；该拼写会被忽略，控制器从 `rv1106.dtsi` 继承 `max-frequency = <200000000>`。

---

## 无法迁出的上游改动

产品改动位于上述目录中。有九个 vendor 文件带有无法迁到那里的修改，因为它们是读取构建开关的地方，而不是声明开关的地方。与上游同步时需要手动合并：

| 文件 | 原因 |
|---|---|
| `media/luckfox/Makefile` | 读取 `RK_ENABLE_LUCKFOX_TEST` |
| `media/sysutils/Makefile` | 读取 `RK_ENABLE_SYSUTILS_TESTS` |
| `media/ive/ive/CMakeLists.txt`、`media/rga/Makefile`、`media/rockit/rockit/mpi/CMakeLists.txt` | 读取 `RK_ENABLE_SAMPLE` 等 |
| `media/cfg/cfg.mk` | `CONFIG_RK_ISP_BUILD_DEMO=n`，是一个值而不是开关 |
| `sysdrv/Makefile` | 传入 `BR2_CCACHE_DIR`；复制 `*_defconfig`，使开发板可以携带自己的 defconfig |
| `sysdrv/tools/board/buildroot/luckfox_pico_defconfig` | `BR2_DL_DIR` |
| `project/build.sh` | 读取 `LF_JOBS`，以及让板子指定自己 recovery 脚本的 `RK_RECOVERY_LUNCH_SCRIPT` |

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

## 发布

`scripts/mk-release.sh` 把一次已完成的 SDK 构建装配成发布包，布局与 v1.0.0 相同：`images/` 下的全部镜像、`LICENSE`、`THIRD-PARTY.md`、`licences/`、填好两个仓库精确 revision 的 `SOURCES.md`、一份 `README.md`，以及覆盖所有文件的 `SHA256SUMS`。它不做构建；先跑 `./build.sh`。

```bash
project/app/motionsense/scripts/mk-release.sh --version v1.1.0
# -> output/release/MotionSense-v1.1.0-luckfox-pico-pro-max-img.zip
# -> output/release/MotionSense-v1.1.0-luckfox-pico-pro-max-update.tar
```

zip 用来通过 USB 烧录板子。tar 是给运行中的板子用的升级包，由 `scripts/mk-update.sh` 打出；见*升级*一节。

板型默认取 `.BoardConfig.mk` 指向的目录，并与 `--board` 核对，所以不会把一块板的镜像装进另一块板的包里。文件名里的板型简称来自脚本内的 `slug_for()`，新板型在那里加一行。

版本号来自 `scripts/version.sh`：设置了 `$MS_VERSION` 就用它，否则取 HEAD 上的 tag，再否则是 `dev-<短 sha>`，有未提交的改动时加上 `-dirty`。agent 的每一种构建方式都问同一个脚本，并把结果编进程序，所以 `/api/status` 里的 `version` 就是镜像构建自哪个版本。发布流程在构建时设置 `MS_VERSION`，因为 tag 要到发布时才会打到这个仓库上。

脚本还会核对 `project/app/out/bin` 里的两个二进制与 `output/out/oem/usr/bin` 里的逐字节一致、`oem.img` 不早于它们。这是针对一类具体的失败：build_app 中途失败（例如没有 go）时，`./build.sh firmware` 会把空的 `app_out` 打进 oem 并报成功，刷出来的板子上没有 MotionSense。

SDK 仓库的 `.github/workflows/release.yml` 在推送 `motionsense-vX.Y.Z` tag 时跑同样的流程：在 `.devcontainer/Dockerfile` 的镜像里构建、缓存 `dl/` 和 `.buildroot-ccache`、调用本脚本，然后以 `vX.Y.Z` 在 MotionSense 仓库发布，tag 打在 SDK 该提交所指向的子模块 commit 上。需要在 SDK 仓库配置 secret `MOTIONSENSE_RELEASE_TOKEN`（只对 MotionSense 仓库有 Contents 读写权限的 fine-grained token）。`workflow_dispatch` 只构建不发布。多板型时在 workflow 的 matrix 里各加一行 `board` / `slug`。

发布说明按下面的规则决定：

- 本仓库里存在 `docs/releases/vX.Y.Z.md`（以 SDK 所指向的子模块 commit 为准），就用它做正文，直接发布。想提前写好的版本走这条路，说明和代码一起进仓库。
- 没有这个文件、且是补丁版（`vX.Y.Z`，Z 大于 0）：用 GitHub 自动生成的改动列表，直接发布。
- 没有这个文件、且是小版本或大版本（`vX.Y.0`）：资产照常上传，但建成 **draft**，在 GitHub 上写完说明再点 Publish。draft 不建 tag，tag 在 Publish 时打在同一个 commit 上。

三种情况正文末尾都会附上两个仓库的精确 commit。已发布的版本都在 `docs/releases/` 下留一份，内容与 GitHub 上的正文一致。

---

## 已验证

用本目录树构建的完整镜像已烧录到 Pico Pro Max 上并运行：开发板以 `rv1106g-motionsense-pro-max.dts` 启动，SD 卡以读写方式自动挂载，两个守护进程自动启动，ISP 以 2304x1296 初始化传感器，HLS 分段和按天生成的 `EventLogs.db` 写入 `DCIM`，agent 连接到帧 socket，`/api/stream` 以每帧 44.7KB 提供 15.0 fps。

## 许可

`../LICENSE` 为 MIT，覆盖此处编写的代码。`THIRD-PARTY.md` 划定了与其他所有内容的边界：Rockchip OSD 源码（3-clause BSD）、DejaVu 字体、Video.js（Apache-2.0）、media-server（MIT，submodule），以及 Rockchip media 库——这些库被引用但不随本项目分发。

---

由 Claude（Opus 5）根据 SDK 源码及在 Luckfox Pico Pro Max 上的测试编写。由 ZIXUAN ZHU 审阅。
