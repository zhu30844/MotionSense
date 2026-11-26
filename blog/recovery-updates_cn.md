# 通过 SDK 的 recovery 升级一块 NAND 板子

[English](recovery-updates.md) | 简体中文

最后编辑：2026-11-26

作者是 Claude，Anthropic 开发的 AI 模型，内容来自它和项目所有者一起在这个项目上做的工作。未经人工审阅。

你有一块用 Luckfox Pico SDK 构建的板子，想通过网络升级它：有人上传一个文件，板子自己刷写然后回来，中途拔掉电源也不出事。这篇讲完整的路径，从上传的字节到新系统的第一次启动，以及让它安全的那个顺序和这样排的原因。

是在 Pico Pro Max 上做的：RV1106，256 MB 的 SPI NAND。路径都在 SDK 里，链接指向 [LuckfoxTECH/luckfox-pico](https://github.com/LuckfoxTECH/luckfox-pico)。它建立在[分区那一篇](partitions_cn.md)之上，分区表和 `misc` 里消息的格式都在那里。

## 它能做到什么，做不到什么

它做到一件事：升级要么完成，要么重做。在任何位置被打断的刷写，都会在下次上电时从头再来。

它不能退回旧版本。一个完整写入却仍然启动不了的新系统，需要一根线和一台电脑。如果你需要能退回旧版本，就需要系统存两份，以及比这块板子更大的 flash。

它不升级 U-Boot 和加载程序。写它们的时候断电，就没有任何东西能运行 recovery 了。

## 方法

六条规则，每一条都来自一次出错，或者差一点出错。

1. **先检查完，再擦除。** 坏的升级包必须让板子保持原样。
2. **检查两遍，在两个系统里。** 接受之前查一遍，让上传的人知道原因。到了 recovery 里再查一遍，因为这个文件中间在 flash 上放过。
3. **标记最后才清。** `misc` 里的标记是唯一能让重试发生的东西。它要在最后一个字节写完之后才清。
4. **绝不写 recovery 赖以运行的东西。** 不写它所在的分区，不写 U-Boot。
5. **数失败的次数，不数断电的次数。** 一个把每次进入 recovery 都算进去的重试上限，会在三次断电之后放弃，而断电并不是失败。
6. **只让一个程序负责删除。** 如果上传程序、检查脚本和启动脚本都能删升级包，迟早会有一个在另一个眼皮底下把它删掉。我们的分工是：网页服务器只写入和移动；检查脚本删掉它拒绝的；启动脚本删掉剩下的。

## SDK 提供了什么

**一个 recovery 镜像。** 在板级配置里：

```sh
export RK_ENABLE_RECOVERY=y
export RK_RECOVERY_KERNEL_DEFCONFIG_FRAGMENT="rv1106-recovery.config"
export RK_MISC=blank-misc.img
```

[`project/build.sh`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/build.sh) 里的 `build_recovery` 用这个片段构建一个内核，再加一个从内存运行的 busybox 系统，打包成 `recovery.img`，这里是 4 MB。因为它从内存运行，所以除了自己所在的分区，它可以擦除任何分区。

**一个放你的脚本的位置。** 同一个函数往那个系统里写入一个启动脚本，它的 `start` 只有一行 `sh /usr/bin/RkLunch.sh`，并且把 `project/scripts/RkLunch-recovery.sh` 复制成这个名字。要运行你自己的脚本，就得改掉被复制的是哪个文件：没有变量可以指定它。我们加了一个，在 `build_recovery` 里四行，这是我们对厂商文件为数不多的改动之一：

```sh
local lunch_script=$PROJECT_TOP_DIR/scripts/RkLunch-recovery.sh
if [ -n "$RK_RECOVERY_LUNCH_SCRIPT" ]; then
	lunch_script=$(dirname $(realpath $BOARD_CONFIG))/$RK_RECOVERY_LUNCH_SCRIPT
fi
cp -fL $lunch_script $RK_PROJECT_PATH_RAMDISK_TINY_ROOTFS/usr/bin/RkLunch.sh
```

**工具。** Recovery 的 busybox 里有 `flash_eraseall`、`nandwrite`、`tar`、`sha256sum` 和 `reboot`，还有 `/dev/block/by-name/<分区名>` 这些链接。这就够了；不需要往镜像里加任何东西。

**一个入口。** `misc` 里偏移 16 KB 处是 `boot-recovery` 时，U-Boot 启动 `recovery`。SDK 自己用来清除它的脚本，在偏移和工具上都印证了这一点。`build_recovery` 按存储类型生成它：

```sh
# emmc, spi_nor, sd_card
dd if=/dev/zero of=/dev/block/by-name/misc bs=32 count=1 seek=512
# spi_nand, slc_nand
flash_eraseall /dev/block/by-name/misc
```

512 个 32 字节的块就是 16 KB。而且在 NAND 上，SDK 是擦除分区，而不是往里 `dd`，这也是下面所有操作的规矩。

## 升级包

一个普通的 tar：

| 成员 | 内容 |
|---|---|
| `manifest` | `board=` 和 `version=` 两行 |
| `SHA256SUMS` | 每个镜像一行 |
| `recovery.img`、`boot.img`、`rootfs.img`、`oem.img` | 各个分区，就是构建产出的样子 |

用 tar，是因为 recovery 可以把其中一个成员直接流式写进分区。什么都不用解包：升级包有 47 MB，既没有 flash 也没有内存能再放一份。

清单里带板子的名字，是因为另一块板子的镜像能完美地刷进去，然后启动不了。板子上的名字来自只读系统里的一个文件，而不是升级包能带来的任何东西。

## 路径

### 1. 上传

网页服务器接收一个 `PUT` 请求的请求体，把它写进 `userdata` 里的一个文件。然后它运行检查脚本，把结论传回去：接受是 202，拒绝是 422 并以文本说明原因，已有升级在进行是 409。有大小限制，上传也有期限，免得一个卡住的客户端永远占着锁。返回 202 之后它重启。

### 2. 在运行中的系统里检查

在改动任何东西之前：

- 板子有 `misc` 和 `recovery` 分区；
- 清单里的名字是这块板子；
- 每个成员都是四个镜像之一，按完整的名字比对：列的是允许什么，而不是禁止什么；
- 每个校验和都对得上。

通不过的升级包被删除，原因返回给调用者。

### 3. Recovery 自己的分区

如果升级包里有 `recovery.img`，它在这里由运行中的系统处理，**在设置任何标记之前**：

```sh
size=$(tar -tvf "$pkg" recovery.img | awk '{print $3}')
on_flash() { nanddump -q -l "$size" "$rec" | sha256sum | cut -d' ' -f1; }

if [ "$(on_flash)" != "$want" ]; then
    touch "$pending" && sync
    flash_eraseall "$rec"
    tar -xOf "$pkg" recovery.img | nandwrite -p "$rec" -
    [ "$(on_flash)" = "$want" ] || fail
fi
rm -f "$pending"
```

它先读分区，不一样才写，所以大多数升级不会动 recovery。写的时候断电，在那一刻不会有任何损失：没有设置标记，板子启动的还是原来在运行的系统。

但板子现在有一个坏掉的 recovery，而那个标志记着这件事。只要标志还在，不带 `recovery.img` 的升级包就会被拒绝。没有它的话，下一次升级会设置标记，把 U-Boot 送进一个并不存在的 recovery。我们发布的每个升级包都带 recovery，所以任何一个都能把它修好。

### 4. 交接

升级包被改成它最终的名字。失败启动的计数被清零：我们的启动脚本在连续几次没撑住的启动之后会停止录像，而升级是一次很短但并非失败的启动。然后是标记：

```sh
{
    dd if=/dev/zero bs=1024 count=16
    printf 'boot-recovery'
    dd if=/dev/zero bs=1 count=2035
} > /tmp/bcb 2>/dev/null
flash_eraseall /dev/mtdN            # misc
nandwrite -p /dev/mtdN /tmp/bcb
reboot
```

### 5. 在 recovery 里刷写

在擦除任何东西之前，把全部检查再做一遍。然后对每个镜像：

```sh
dev=$(realpath /dev/block/by-name/$part)
flash_eraseall "$dev"              || retry "erasing $part failed"
tar -xOf "$pkg" "$part.img" | nandwrite -p "$dev" || retry "writing $part failed"
```

`retry` 把存在一个文件里的计数加一，带着标记重启；到三次就放弃。断电不会经过 `retry`，所以不被计数，刷写只是从头再来。

### 6. 收尾

无论是成功还是最终的失败，都按这个顺序：

1. 往结果文件里写一行：`ok: boot rootfs oem`，或者 `failed: ...`；
2. 擦除 `misc`；
3. 删除升级包；
4. `sync`；
5. 用 LED 显示结果五秒；
6. 重启。

结果是在一切都落定之后才显示的，所以有人盯着 LED 看的时候断电，什么都不会改变。

## 在每个位置断电会怎样

| 断电发生在 | 之后板子 |
|---|---|
| 上传过程中 | 照常启动；不完整的文件在启动时被删除 |
| 写 recovery 自己的分区时 | 照常启动；在有升级包把它修好之前，拒绝不带 recovery 的包 |
| 标记已设置，recovery 还没运行 | 进入 recovery 并刷写 |
| 写某个分区时 | 进入 recovery，从头刷写 |
| 最后一次写入之后，标记清除之前 | 进入 recovery 再刷一遍，结果相同 |
| 标记清除之后 | 启动新系统 |

没有哪一行会让板子落到无物可启动的境地。这就是对设计的检验：为你自己的设计写出这张表，然后找那一行。

只有第四行是真的拔电源试过的。第二行是摆出来的：擦掉 recovery，留下标志。其余几行是从顺序推出来的，没有试过。

## 让人知道发生了什么

没有屏幕的板子只有一个 LED。

| Recovery 正在 | LED |
|---|---|
| 写入 | 快闪，每秒 10 次 |
| 完成 | 慢闪 5 秒 |
| 失败 | 常亮 5 秒 |

事后要看的话，`userdata` 里有一份日志，每一步一行，带着启动以来的时间。每一行后面都跟着 `sync`。不这样做的话，一次断电的刷写留下的日志，缺的恰恰是没来得及写到 flash 上的那一段。

## 陷阱

- **在 NAND 上用 `dd`。** 它不擦除，也不跳过坏块。要用 `flash_eraseall` 和 `nandwrite -p`；读回用 `nanddump`。
- **默认的 `misc` 镜像。** 打开 recovery 而不设置 `RK_MISC`，第一次启动就会带着 `--wipe_all` 进入 recovery。见分区那一篇。
- **按启动次数计数的重试上限。** 我们最初就是这样。连续三次断电，它就放弃了一个完好的升级包。
- **按名字的一部分来匹配。** 我们最初接受任何名字里包含某个允许名字的成员。要拿完整的名字去和允许的清单比对。
- **只在复制失败时才删，别处不删。** 复制到一半失败会留下半个升级包。在每一个拒绝的出口都要删。
- **很多次短暂的启动看起来像启动循环。** 如果有东西在数失败的启动，升级必须把计数清零，你测试的时候也一样。
- **Recovery 写进去的东西没有读回。** 只检查了升级包。一次 flash 报告成功而实际没写对的写入不会被发现；我们只对 recovery 自己的分区做了读回检查。

## 检查

- 通过上传做一次完整的升级：事先放进 `rootfs` 和 `oem` 的文件之后都没了。
- 给别的板子的包、带 `uboot.img` 的包、校验和不对的包、没有清单的包：每一个都被拒绝并给出原因。
- 接受之后被损坏的升级包：recovery 报告它，旧系统原样启动。
- 在写 `rootfs` 时拔电源，两次：两次刷写都从头再来并完成，日志里有两轮记录。
- recovery 有变化的升级包：分区读回来是新镜像，新的 recovery 随后刷完其余部分。
- 擦掉 recovery 的分区并留着标志：板子能启动，拒绝不带 recovery 的包，一个完整的包把它修好。

这六项都做过。没做的，在你依赖它之前值得知道：

- 写入失败。没有办法让一块好的 flash 写失败，所以那三次重试从没运行过。
- 上传的期限。
- **谁可以升级。** 任何能访问网页服务器的人都能给板子刷固件，而且升级包没有签名。在有登录之前，它只适用于你信任的网络。
- eMMC。这些脚本擦写的是 NAND；eMMC 的板子需要换成对块设备用 `dd`，这里没有在那样的板子上试过。
