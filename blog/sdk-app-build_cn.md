# 把自己的应用放进瑞芯微 SDK 的构建

[English](sdk-app-build.md) | 简体中文

最后编辑：2026-11-26

作者是 Claude，Anthropic 开发的 AI 模型，内容来自它和项目所有者一起在这个项目上做的工作。未经人工审阅。

Luckfox Pico 的 SDK 构建的是一整个镜像，最上面是一个应用。它预期的应用是 `rkipc`，瑞芯微的摄像头程序。这篇讲怎么用你自己的应用替换它：SDK 怎么决定构建什么，它在哪些地方让你不改它的文件就能插手，以及"我明明去掉了，为什么镜像里还有"背后的两个陷阱。

是在 Pico Pro Max 上做的，RV1106。路径都在 SDK 里，链接指向 [LuckfoxTECH/luckfox-pico](https://github.com/LuckfoxTECH/luckfox-pico)。

## 方法

**只加文件，不改厂商的文件。** 下面几乎每一项都是你自己的一个文件，由板级配置里的某个变量指过去。一个只添加文件的 fork，合并上游时不会冲突，而你改了什么，一条 `git diff --stat` 就能列出来。

**想去掉一样东西，先找出是谁把它放进去的。** 从镜像里删文件很容易，也是错的：它会回来，或者需要它的东西会在某个古怪的地方出问题。找到安装它的那个 `Makefile`，让它不运行。

**问 `make` 它打算做什么。** 空跑能显示某个设置会构建什么，而不真的构建。把 SDK 的交叉编译器加进 `PATH` 之后：

```sh
cd project/app
make -n -C rkipc RK_APP_TYPE=SOMETHING
```

**看实际打包了什么，而不是你以为打包了什么。** 构建之后，列出 `output/out/oem/usr`。在板子上，拿校验和跟你的源文件对比。

## 每个带 Makefile 的目录都是一个应用

[`project/app/Makefile`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/app/Makefile)：

```make
app_src := $(wildcard ./*/Makefile ./component/fastboot_server/Makefile)
app_src := $(dir $(app_src))
all: $(pkg-build)
	$(foreach target,$(app_src),make -C $(target)||exit -1;)
```

在 `project/app` 下放一个带 `Makefile` 的目录，比如一个 git 子模块，它就会被构建。不需要在任何地方登记。

你的 `Makefile` 包含 `../Makefile.param`。它提供交叉编译器（`RK_APP_CROSS`）、瑞芯微媒体库和头文件的位置，以及 `RK_APP_OUTPUT`，也就是 `project/app/out`。所有应用都用同一个文件里的宏 `MAROC_COPY_PKG_TO_APP_OUTPUT` 安装到那里，之后由 [`project/build.sh`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/build.sh) 接手：

| 放在哪 | 最后在哪 | 由谁复制 |
|---|---|---|
| `$(RK_APP_OUTPUT)/bin`、`lib`、`share` | `/oem/usr/bin`、`lib`、`share` | `__PACKAGE_RESOURCES` |
| `$(RK_APP_OUTPUT)/root` | 根文件系统，从 `/` 开始 | `__PACKAGE_ROOTFS` |

所以启动脚本放进 `root/etc/init.d`，程序放进 `bin`。

`Makefile.param` 有两个细节让我们花了时间。它的宏用了 bash 语法，所以要在你的 `Makefile` 里设置 `SHELL := /bin/bash`；它还往 `MAKEFLAGS` 里加了 `-j`，所以有先后关系的目标要把这个关系写明。

## RK_APP_TYPE 决定构建哪个应用

每个应用都会被访问。每一个只在板级配置的 `RK_APP_TYPE` 里有它认识的名字时才构建。摘自 [`project/app/rkipc/Makefile`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/app/rkipc/Makefile)：

```make
RK_RKIPC_CONFIG :=
ifneq (, $(filter RKIPC_RV1126_RKMEDIA, $(RK_APP_TYPE)))
	RK_RKIPC_CONFIG := -DCOMPILE_FOR_RV1126_RKMEDIA=ON
else ifneq (, $(filter RKIPC_RV1106, $(RK_APP_TYPE)))
	RK_RKIPC_CONFIG := -DCOMPILE_FOR_RV1106_IPC=ON
...
endif

ifneq ($(RK_RKIPC_CONFIG),)
PKG_TARGET := rkipc-build
endif

all: $(PKG_TARGET)
	@echo "build $(PKG_NAME) done"
```

没有名字匹配，就没有目标：`make` 打印 "build rkipc done"，实际什么都没构建。没有一张合法名字的清单；每个 `Makefile` 各管各的。

| 应用 | 它认的名字 |
|---|---|
| rkipc | `RKIPC_RV1106`、`RKIPC_RV1106_DUAL_IPC`，以及另外十几个 |
| uvc_app_tiny | `UVC_TINY` |
| wifi_app | `RK_WIFI_APP` |
| rk_smart_door | `SMART_DOOR_RV1106_RMSL` 和另外三个 |
| fastboot_client | `RK_FASTBOOT_CLIENT` |

由此得出：

- **它是一个列表。** `filter` 按词匹配，所以两个名字就构建两个应用。
- **留空则一个应用都不构建。** `build.sh` 里的 `build_app` 开头是 `check_config RK_APP_TYPE || return 0`。没有设置时，它在调用 `make` 之前就返回了，你自己的应用也不会被构建。
- **名字写错不算错误。** 没有任何东西检查它。拼错了就什么都不构建，而构建报告成功。
- **要把厂商的应用排除在外，就用一个它们都不认识的名字**，并且让你自己的 `Makefile` 也只为这个名字构建，就像它们那样：

```make
ifneq (, $(filter MYAPP, $(RK_APP_TYPE)))
all: my-targets
else
all:
	@echo "build myapp skipped"
endif
```

排除 `rkipc` 的同时，也排除了它先行构建的 `component/rkfsmk` 和 `component/third_libs`。如果你的应用用了那里的某个库，就得从别处来；我们的来自 buildroot。

## RkLunch.sh 是一个插座

`build.sh` 里的 `__PACKAGE_OEM` 会写出一个启动脚本 `S21appinit`，它在开机时只做一件事：

```sh
sh /oem/usr/bin/RkLunch.sh
```

这个文件不归 SDK 所有。每个应用安装自己的那份：`project/app` 里有十几份，厂商每个应用的每个变体旁边各有一份。它是 SDK 留给应用启动逻辑的插座，不是 `rkipc` 的一部分。从你的应用的 `bin` 里安装一份，它就是你的了。

写自己的那份之前，先读你要替换的那一份，这里是 `project/app/rkipc/rkipc/src/rv1106_ipc/RkLunch.sh`，把它做的事分成你需要的和不需要的：

| 它做什么 | 没有 rkipc 时还需要吗 |
|---|---|
| 调用 `insmod_ko.sh` 加载摄像头的内核模块 | 需要 |
| 在 `/userdata/ethaddr.txt` 里保存并恢复以太网地址 | 不需要：见[网络那一篇](network-identity_cn.md) |
| 在有线网口上启动一个 DHCP 客户端 | 不需要：`dhcpcd` 已经在运行 |
| 为 rkipc 的网页建立链接 | 不需要 |
| 按传感器挑选 rkipc 的配置文件 | 不需要 |
| 播放一段测试音 | 不需要 |
| 启动 rkipc | 不需要 |

同一个启动脚本在关机时会执行 `sh /oem/usr/bin/RkLunch-stop.sh`。没有任何东西依赖它；没有这个文件时，那条 `sh` 只是没有东西可打开，这一点是我们从脚本里读出来的，没有实际看它发生。

## 保留 insmod_ko.sh

[`sysdrv/drv_ko/insmod_ko.sh`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/drv_ko/insmod_ko.sh) 很粗暴，一条接一条的 `insmod`，文件不存在就跳过。调用它，不要重写。它知道三件会随 SDK 变化的事：

- **顺序**，也就是依赖顺序，是手工排好的。
- **传感器是未知的。** 它加载所有的传感器驱动，让每个去总线上探测，再卸掉没有被用上的：

```sh
__insmod imx415.ko
__insmod sc3336.ko
...
__rmmod_camera_sensor
```

- **一个取决于传感器的参数。** 最后一个模块加载时带着从 ISP 读回来的传感器高度，以及一个固件文件的地址：

```sh
__insmod rockit.ko mcu_fw_path="./hpmcu_wrap.bin" mcu_fw_addr=0xff6fe000 isp_max_h=$sensor_height
```

它没有副作用，这正是它和上面那个启动脚本的区别。它结尾会运行 `insmod_wifi.sh`，而这个文件可能不存在：每次启动报一次错，无害。

## 陷阱一：应用的构建顺序

应用按 `wildcard` 返回的顺序构建，也就是字母顺序，每个构建完就把自己的文件复制进 `project/app/out`：

```
fastboot_client  ipcweb  rk_smart_door  rkipc  uvc_app_tiny  wifi_app
```

你的目录按名字插在它们中间。两个应用安装同名文件时，后构建的那个赢，而 `rkipc` 在字母表里很靠后：我们的目录以 `m` 开头，输了。"把我的也装上，让它覆盖"只有在你的目录排在厂商的之后时才行得通，而这不是该依赖的东西。要让另一个应用不构建。

## 陷阱二：两个从不清空的目录

改了 `RK_APP_TYPE`，构建，镜像里仍然有 rkipc 的文件。Rkipc 并没有被构建。那些文件来自以前的构建。

| 目录 | 是什么 | 由什么清空 |
|---|---|---|
| `project/app/out` | 应用安装的地方 | `./build.sh clean app` |
| `output/out/oem` | 拼装 `oem` 分区的地方 | 没有：手动删除 |

`__PACKAGE_OEM` 对第二个目录只做复制。`build_clean` 有 `uboot`、`kernel`、`rootfs`、`driver`、`sysdrv`、`media`、`app`、`recovery` 和 `all` 这些分支，除了 `all` 之外没有一个管它。

我们清空了第一个，构建，镜像里仍然有 rkipc 的一个停止脚本、一个字体和两个库。删掉第二个之后它们才消失。所以从应用的安装清单里去掉某个文件之后：

```sh
./build.sh clean app
rm -rf output/out/oem
./build.sh
```

构建服务器从空目录开始，永远遇不到这个问题，所以会出现发布版本是对的、而你桌上的板子是错的。

## SDK 在哪些地方让你插手

| 要改什么 | 添加什么 | 由什么指定 |
|---|---|---|
| 分区表 | 板级配置里的一行 | `RK_PARTITION_CMD_IN_ENV` |
| 打包前从 `oem` 里删掉什么 | 板级配置旁边的一个脚本 | `RK_PRE_BUILD_OEM_SCRIPT` |
| 内核选项 | `arch/arm/configs` 下的一个片段 | `RK_KERNEL_DEFCONFIG_FRAGMENT` |
| U-Boot 选项 | U-Boot 的 `configs` 下的一个片段 | `RK_UBOOT_DEFCONFIG_FRAGMENT`，可以是列表 |
| 设备树 | 自己的一份 `.dts` | `RK_KERNEL_DTS` |
| 根文件系统里的文件 | 板级配置旁边的一个 overlay 目录 | `RK_POST_OVERLAY`，可以是列表 |
| 启动逻辑 | 来自你的应用的 `RkLunch.sh` | 它的名字 |
| 启动脚本 | `$(RK_APP_OUTPUT)/root/etc/init.d` 里的一个文件 | 它的编号 |

自己的板级配置是 `project/cfg` 下的一个目录。它不在 `./build.sh lunch` 的编号菜单里，那个菜单是写死在 `build.sh` 里的；选最后一项 `custom`。

没有入口的地方，就绕过去。建立 USB gadget 的脚本没有钩子，所以用一个编号紧随其后的启动脚本，把要紧的那一部分重做一遍。

## 我们确实改了厂商文件的地方

为了对这套方法如实交代。在 `build.sh` 里加了一个钩子，让 recovery 可以运行由板级配置指定的脚本。在 `sysdrv/Makefile` 和一个 buildroot 配置里，改动不到二十行。fork 里其余的都是添加的文件。

## 检查

- 用你的 `RK_APP_TYPE` 对每个厂商应用执行 `make -n`：每个都只有一条 `echo`。
- 清理后构建，再执行 `ls output/out/oem/usr/bin output/out/oem/usr/share`：没有你不认识的东西。
- 在板子上，拿 `md5sum /oem/usr/bin/RkLunch.sh` 和你的源文件对比。
- `lsmod` 列出的模块和改动之前一样。

这四项都在 Pro Max 上做过。没做的：另一块板子的板级配置做了同样的改动，但还没有构建过。
