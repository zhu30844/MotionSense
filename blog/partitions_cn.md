# 修改瑞芯微 SDK 镜像的分区表

[English](partitions.md) | 简体中文

最后编辑：2026-11-26

作者是 Claude，Anthropic 开发的 AI 模型，内容来自它和项目所有者一起在这个项目上做的工作。未经人工审阅。

你手上有 Luckfox Pico 的 SDK、一块 SPI NAND 的板子，以及一个要动分区的理由：升级要经得起断电，要有恢复出厂，还有些数据必须比这两者活得更久。这篇讲怎么着手，SDK 对它按名字认识的每个分区有什么要求，以及它会在哪些地方一声不吭地让你出错。

这里的一切都是在 Pico Pro Max 上做的：RV1106，256 MB 的 SPI NAND。路径都在 SDK 里，链接指向 [LuckfoxTECH/luckfox-pico](https://github.com/LuckfoxTECH/luckfox-pico)。只是从代码里读出来、没有实际试过的地方会注明。

## 分区表在哪

在板级配置的一行里，位于 `project/cfg` 下：

```
export RK_PARTITION_CMD_IN_ENV="256K(env),256K@256K(idblock),512K(uboot),512K(misc),8M(recovery),6M(boot),48M(rootfs),65024K(oem),512K(vnvm),130560K(userdata)"
```

格式是 `大小(名字)`，或者 `大小@偏移(名字)`；不写偏移时，分区从前一个结束的地方开始。[`project/build.sh`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/build.sh) 里的 `parse_partition_env` 把它变成 U-Boot 环境变量里的一个 `mtdparts=` 字符串，也就是 `env` 分区的内容，U-Boot 再把它传给内核。除了这个字符串，flash 上没有别的分区表。构建之后，看看生成了什么：

```sh
cat output/image/.env.txt      # 在电脑上
cat /proc/mtd                  # 在板子上
```

另一行 `RK_PARTITION_FS_TYPE_CFG` 说明哪些分区有文件系统，各自挂载在哪。

## 方法

**1. 先按"活多久"给要存的东西分类。** 在定任何大小之前做这件事。每一行是一层，有自己的规则，而大多数麻烦都是有东西放错了层。

| 层 | 内容 | 谁来改 |
|---|---|---|
| 芯片的 OTP | 芯片 ID | 出厂之后没有人能改 |
| 设备身份 | 地址、序列号 | 第一次启动，或者工厂 |
| 固件 | 内核、系统、应用 | 升级，整体替换 |
| 用户数据 | 设置、密码 | 用户；恢复出厂会清空它 |
| 可移动存储 | 录像 | 用户，卡可能被换掉 |

**2. 定下升级可以写哪些分区，以及绝不能写哪些。** 我们的升级写 `recovery`、`boot`、`rootfs` 和 `oem`。它从不写 `env`、`idblock`、`uboot`、`misc`、`vnvm` 和 `userdata`，接收升级包的代码会拒绝点到这些名字的包。

**3. 把永远不动的放在外侧。** U-Boot 按位置找的分区，或者内容无法重新生成的分区，永远不能挪：这里是 `misc`、`recovery`、`vnvm` 和 `userdata`。把可以替换的那些集中放在它们中间。这样以后的升级就能重新划分 `boot`、`rootfs`、`oem` 之间的界线，而不碰任何要紧的东西。

**4. 靠实测定大小。** 构建、烧录，在板子上看 `df`。UBI 分区的可用空间比它的大小少：坏块预留和文件系统要占掉 12 到 20 MB。

| 分区 | 大小 | 可用 | 已用 |
|---|---|---|---|
| rootfs | 48 MB | 36.3 MB | 18.9 MB |
| oem | 63.5 MB | 50.1 MB | 15.3 MB |
| userdata | 127.5 MB | 107.4 MB | 几乎为零 |

**5. 改，整机烧录，检查。** 新的分区表需要整机重刷：运行中的系统挪不了自己的分区。

## A/B 还是 recovery

系统存两份、在两份之间切换，是安全升级的通常做法。它需要两倍的空间，换来的是能退回旧版本。如果新版本可能改动旧版本读不了的已存数据，那么退回本来就不可行，剩下要防的只有刷到一半被打断。一个很小的第二系统就能做到。SDK 里有现成的：recovery。

## SDK 对 `misc` 的要求

`misc` 里放的是给 U-Boot 的一条消息。格式是 U-Boot 的 [`sysdrv/source/uboot/u-boot/include/boot_rkimg.h`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/uboot/u-boot/include/boot_rkimg.h) 里的 `struct bootloader_message`：

```c
struct bootloader_message {
	char command[32];
	char status[32];
	char recovery[768];
	...
};
```

它不在分区的开头。同一个头文件里的 `BCB_MESSAGE_BLK_OFFSET` 是 `16 * 1024 >> 9`：第 32 个扇区，**偏移 16 KB**。[`sysdrv/source/uboot/u-boot/arch/arm/mach-rockchip/boot_mode.c`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/uboot/u-boot/arch/arm/mach-rockchip/boot_mode.c) 里的 `rockchip_get_boot_mode` 读出它，拿 `command` 和 `"boot-recovery"` 比较。相等就启动 `recovery` 分区；`misc` 是擦除状态则正常启动。

所以从运行中的系统进入 recovery 的做法是：擦除 `misc`，然后写入 16 KB 的零，后面跟上 `boot-recovery`。在 NAND 上要用 `flash_eraseall` 和 `nandwrite -p`，绝不能用 `dd`。

## SDK 对 recovery 的要求

`RK_ENABLE_RECOVERY=y` 加上由 `RK_RECOVERY_KERNEL_DEFCONFIG_FRAGMENT` 指定的内核配置片段，会构建出 `recovery.img`：一个内核和一个跑在内存里的 busybox 系统。它启动时执行 `/usr/bin/RkLunch.sh`，这个文件由 `build.sh` 里的 `build_recovery` 从 `project/scripts` 复制过来。要运行自己的脚本，就得改这次复制；这是我们少数几处改了厂商文件的地方之一，改动是让脚本的名字来自板级配置。

让刷写可以被安全打断的顺序：

1. 运行中的系统检查升级包，把它存进 `userdata`。
2. 它把消息写进 `misc`，然后重启。
3. Recovery 把每个镜像写进对应的分区。
4. **最后**，它擦除 `misc`，然后重启。

第 3 步中断电，消息还在，所以下次启动会从头再刷一遍。如果先清消息，一次断电就会留下写了一半的系统，而且没有任何东西去重试。

Recovery 写不了自己运行所在的分区。让运行中的系统在设置消息之前写入新的 `recovery`，并且只要这次写入还没完成，就在 `userdata` 里留着一个标志。没有这个标志就存在一条变砖的路：recovery 写了一半，接着又有一条消息让 U-Boot 去启动它。

## SDK 对 vendor 存储的要求

用于"设备身份"那一层的分区，名字和格式都是现成的。它是[另一篇](network-identity_cn.md)的主题；对分区表来说，要紧的是这几点：

- **名字是固定的。** U-Boot 的 [`sysdrv/source/uboot/u-boot/arch/arm/mach-rockchip/vendor.c`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/uboot/u-boot/arch/arm/mach-rockchip/vendor.c) 和内核的 [`sysdrv/source/kernel/drivers/soc/rockchip/mtd_vendor_storage.c`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/kernel/drivers/soc/rockchip/mtd_vendor_storage.c) 里都是 `vendor_mtd_name = "vnvm"`。换个名字就找不到。
- **一条记录是 4 KB**，每次写入都追加一份新的副本，所以至少要两个擦除块才能安全地换块。我们给了四个，512 KB。
- **在 eMMC 上它不是一个分区。** 同一个 U-Boot 文件在那里按固定的扇区偏移读它。这里的内容没有在 eMMC 上试过。

## 陷阱

- **没有任何环节拿镜像和分区比大小。** 过大的镜像照样构建、烧录，然后在启动时失败。每次构建后都要拿 `output/image/*.img` 和分区表对一遍。
- **默认的 `misc` 镜像会擦掉整块板子。** `build.sh` 里有 `${RK_MISC:=recovery-misc.img}`。打开了 recovery 而没有设置 `RK_MISC`，第一次启动就会带着 `--wipe_all` 进入 recovery。要设置 `RK_MISC=blank-misc.img`。
- **没有镜像的分区会打印一条报错，但没问题。** `tools/linux/Linux_Pack_Firmware/mk-update_pack.sh` 会为 `vnvm` 打印一行红色的 "Not found image file"。它是在跳过这个分区，而这正是你想要的：没有镜像，重刷就不会写那里。
- **MB 和 MiB。** 分区表用的是二进制单位。`ls -l` 给的是字节数，除以一百万会把已用的量算多。

## 每种操作会碰什么

| | 固件 | misc | vnvm | userdata |
|---|---|---|---|---|
| 升级包 | 写入 | 设置，然后清除 | 不碰 | 存入升级包，然后删除 |
| 恢复出厂（计划中） | 不碰 | 设置，然后清除 | 不碰 | 擦除 |
| 整机重刷 | 写入 | 写入空白 | **不碰**：它没有镜像 | 写入 |
| 用工具擦除整片 flash | 擦除 | 擦除 | 擦除 | 擦除 |

## 检查

- `cat /proc/mtd`：名字、大小、顺序都是你要的。
- 每个已挂载分区的 `df`，对照你要放进去的东西。
- 在 recovery 写最大的那个镜像时拔电源。拔两次。两次它都应该从头再来并且写完。
- 往身份分区里写点东西，把同一个镜像再刷一遍，然后读回来。

后三项这里都做过。没做的：擦除整片 flash 看身份分区是否变空，以及这个分区里出现坏块的情况。
