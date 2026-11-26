# 让一块板子的网络地址固定下来

[English](network-identity.md) | 简体中文

最后编辑：2026-11-26

作者是 Claude，Anthropic 开发的 AI 模型，内容来自它和项目所有者一起在这个项目上做的工作。未经人工审阅。

用 Luckfox Pico SDK 构建出来的板子，除非有东西拦着，每次启动都会换一个以太网地址，USB 网络的那一对地址也一样。这篇讲怎么查出一个地址是从哪来的，瑞芯微原本想让它怎么工作，涉及的确切格式，以及怎么在不改厂商代码的前提下让地址固定下来。

是在 Pico Pro Max 上做的：RV1106，SPI NAND。路径都在 SDK 里，链接指向 [LuckfoxTECH/luckfox-pico](https://github.com/LuckfoxTECH/luckfox-pico)。只是从代码里读出来、没有实际试过的地方会注明。

## 方法：问板子，地址是谁设的

不要从源码开始。运行中的板子上有三样东西，能告诉你大部分答案。

**最后是谁设的。** 内核记着每个网口的地址是怎么来的：

```sh
cat /sys/class/net/eth0/addr_assign_type
```

| 值 | 含义 |
|---|---|
| 0 | 交给驱动的：来自硬件或设备树 |
| 1 | 内核随机生成的 |
| 3 | 启动之后有程序设置过 |

**引导程序传了什么。** 在内核启动时拿到的设备树里找地址，再和源码里的 `.dts` 对比：

```sh
hexdump -C /sys/firmware/devicetree/base/ethernet@ffa80000/local-mac-address
```

板子上有而源码里没有，就是 U-Boot 放进去的。

**启动过程做了什么。** 在开机时运行的脚本里搜 `hw ether`，以及你不认识的文件名。

在这块板子上，三个答案分别是：3；一个每次启动都变的地址；一个脚本，它把第一次看到的地址存进 `/userdata/ethaddr.txt`，之后每次启动再把它设回去。我们原先猜地址是内核生成的。第二项检查表明是 U-Boot。先查，再解释。

## 这条链，在源码里

**U-Boot 生成或读取地址。** [`sysdrv/source/uboot/u-boot/arch/arm/mach-rockchip/board.c`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/uboot/u-boot/arch/arm/mach-rockchip/board.c) 里的 `rockchip_set_ethaddr`，在 `CONFIG_ROCKCHIP_SET_ETHADDR` 打开时由 `board_late_init` 调用：

```c
#define MAX_ETHERNET	0x2
...
	u8 ethaddr[ARP_HLEN * MAX_ETHERNET] = {0};
#ifdef CONFIG_ROCKCHIP_VENDOR_PARTITION
	ret = vendor_storage_read(LAN_MAC_ID, ethaddr, sizeof(ethaddr));
#endif
	for (i = 0; i < MAX_ETHERNET; i++) {
		if (ret <= 0 || !is_valid_ethaddr(&ethaddr[i * ARP_HLEN])) {
			if (!randomed) {
				net_random_ethaddr(&ethaddr[i * ARP_HLEN]);
			...
			need_write = true;
		}
		...
		env_set(mac, buf);          /* "ethaddr", then "eth1addr" */
	}
#ifdef CONFIG_ROCKCHIP_VENDOR_PARTITION
	if (need_write)
		ret = vendor_storage_write(LAN_MAC_ID, ethaddr, sizeof(ethaddr));
#endif
```

把它当作厂商的设计来读：从 vendor 存储里取地址；没有的话生成一个，**并且写回去**，这样骰子只掷一次。工厂往里写入买来的地址，骰子就一次都不用掷。

**U-Boot 把它交给内核。** `sysdrv/source/uboot/u-boot/common/fdt_support.c` 里的 `fdt_fixup_ethernet` 把 `ethaddr` 复制到别名 `ethernet0` 所指节点的 `local-mac-address` 里。`rv1106.dtsi` 里有 `ethernet0 = &gmac`。没有这个别名，什么都传不过去。

**内核使用它。** [`sysdrv/source/kernel/drivers/net/ethernet/stmicro/stmmac/dwmac-rk.c`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/kernel/drivers/net/ethernet/stmicro/stmmac/dwmac-rk.c) 里的 `rk_get_eth_addr` 如果拿到了合法的地址就直接返回。否则它做和 U-Boot 一样的事：读 vendor 存储，读不到就生成一个并写回去。

**为什么在这块板子上每次启动都是随机的。** Luckfox 的配置没有打开 `CONFIG_ROCKCHIP_VENDOR_PARTITION`，也没有对应的分区。上面两段 `#ifdef` 编译出来都是空的，只剩下骰子。`/userdata` 里的那个文件，是一个脚本在高了一层的地方做"写回去"这一步，它能撑到有东西擦掉 `/userdata` 为止。

## Vendor 存储

一小块存储，放只属于一台设备的东西。打开它不需要写代码：

| 位置 | 内容 |
|---|---|
| 分区表 | 一个名叫 `vnvm` 的分区；见[分区那一篇](partitions_cn.md) |
| U-Boot | `CONFIG_ROCKCHIP_VENDOR_PARTITION=y` |
| 内核 | `CONFIG_ROCKCHIP_VENDOR_STORAGE=y` 和 `CONFIG_ROCKCHIP_MTD_VENDOR_STORAGE=y` |

把这些选项放进自己的配置片段里，在板级配置中指定它们；不用改厂商的任何文件。

### 项

存进去的每样东西是一个带编号的项。编号在 [`sysdrv/source/kernel/include/linux/soc/rockchip/rk_vendor_storage.h`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/kernel/include/linux/soc/rockchip/rk_vendor_storage.h) 里：

| 编号 | 名字 | 内容 |
|---|---|---|
| 1 | `SN_ID` | 序列号 |
| 2 | `WIFI_MAC_ID` | Wi-Fi 地址 |
| 3 | `LAN_MAC_ID` | 以太网地址 |
| 4 | `BT_MAC_ID` | 蓝牙地址 |
| 5 到 17 | | 密钥、校准数据等 |

17 以上没有定义，所以更大的编号归你用。我们用的是 200。

### 在 flash 上

[`sysdrv/source/kernel/drivers/soc/rockchip/mtd_vendor_storage.c`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/source/kernel/drivers/soc/rockchip/mtd_vendor_storage.c) 里的 `struct vendor_info`：

```c
struct vendor_item { u16 id; u16 offset; u16 size; u16 flag; };

struct vendor_info {
	u32	tag;            /* 0x524B5644, "RKVD" */
	u32	version;
	u16	next_index;
	u16	item_num;
	u16	free_offset;
	u16	free_size;
	struct	vendor_item item[62];
	u8	data[MTD_VENDOR_PART_SIZE * 512 - 512 - 8];
	u32	hash;
	u32	version2;       /* equal to version in a complete record */
};
```

一条记录是 4 KB。每次写入都追加一条完整的新记录，版本号加一，读的时候取两个版本号字段一致的记录里版本最高的那条：被断电打断的写入会被忽略，它之前的那条仍然有效。直接从分区里读原始内容，一块只存了以太网地址的板子是这样的：

```
00000000  44 56 4b 52 02 00 00 00  00 00 01 00 40 00 b8 0d  |DVKR........@...|
00000010  03 00 00 00 0c 00 00 00  00 00 00 00 00 00 00 00  |................|
00000200  32 bf fe 76 41 1a 36 bf  fe 76 41 1a 00 00 00 00  |2..vA.6..vA.....|
```

先是标签、版本 2、一个项；然后是项表：编号 3、偏移 0、大小 12；再然后，在 0x200 处，是数据。

### 在程序里

内核会创建 `/dev/vendor_storage`。在同一个源文件里：

```c
struct rk_vendor_req {
	u32 tag;        /* VENDOR_REQ_TAG, 0x56524551 */
	u16 id;
	u16 len;
	u8 data[1024];
};
#define VENDOR_READ_IO   _IOW('v', 0x01, unsigned int)
#define VENDOR_WRITE_IO  _IOW('v', 0x02, unsigned int)
```

填好 `tag`、`id` 和 `len`，调用 `ioctl`。读一个从没写过的项会失败。SDK 在 `project/app/rkipc/rkipc/common/vendor_storage` 下有一份示例。shell 做不了这件事，所以需要一个小程序。

## 陷阱：以太网那一项是两个地址

第 3 项是**十二个字节：两个地址**，不管板子实际有几个网口。这就是上面 U-Boot 里的 `MAX_ETHERNET 0x2` 和 `dwmac-rk.c` 里的 `MAX_ETH 2`；RV1106 只有一个网口，但它和有两个网口的芯片共用这份代码。

再看一遍那个循环。U-Boot 两个都校验。如果你只写六个字节，第二个地址读出来是全零，不合法：U-Boot 会给它生成一个，置上 `need_write`，然后把这一项写回去。你的代码随后发现这一项变了，又把自己的六个字节写一遍。每次启动写两次 flash，永远如此。所以两个地址都要写。第二个可以是任何固定的合法值；只有一个网口的板子上没有东西用它。

这是从代码里读出来的。实际试过的是：两个都写了之后，这一项在多次启动中没有再变过。

## 选地址

**形式。** 没有花钱买的地址必须是本地管理地址：第一个字节的第 1 位置一、第 0 位清零。这样第二个十六进制数字就是 2、6、a 或 e。这一位也正是用来区分自己生成的地址和买来的地址的。

**来源。** 板子生来就有、永远不变的东西：芯片 ID。紧挨着上面那个函数的 `rockchip_set_serialno` 从 OTP 读出 16 个字节，用 CRC32 折叠成序列号，它就是 `/proc/cpuinfo` 里的 `Serial`。把它和网口的名字一起做哈希，取六个字节，把那两位调好：

```sh
serial=$(sed -n 's/^Serial[^:]*: *//p' /proc/cpuinfo)
h=$(printf 'myproduct eth0 %s' "$serial" | sha256sum)
printf '%02x:%s\n' $(( (0x${h:0:2} & 0xfc) | 2 )) "$(echo "${h:2:10}" | sed 's/../&:/g; s/:$//')"
```

哈希里带上名字，一个序列号就能给每个网口各算出一个地址。事先要检查序列号不是全零。

**在哪做。** Vendor 存储本身就是钩子。U-Boot 最先读它，所以你自己的脚本把算出来的地址写进去，就决定了 U-Boot 从下次启动起用什么。同时也要把它设到网口上，供正在进行的这次启动使用。代价是空白板子的第一次启动，有几秒钟用的是 U-Boot 随机的地址。

改 `rockchip_set_ethaddr` 让它自己推导，可以省掉这几秒，大约十几行。但那是对厂商文件的修改，以后每次合并上游都要带着。我们没有改。

**什么不能替换。** 我们最后定下的规则：

| vendor 存储里是什么 | 怎么做 |
|---|---|
| 什么都没有 | U-Boot 存入一个随机地址；替换它 |
| 本地管理的地址 | 替换它 |
| 其他任何地址 | 不动：那是工厂写的 |
| 第 200 项的内容是 `01` | 不动，不管地址是什么 |

最后一行之所以存在，是因为前三行不够。手工挑地址的人应该挑一个本地管理的地址，而一个比特分不出它和随机地址。地址旁边的一个标记可以。

## USB 网络

处在 USB 设备模式的板子，在电脑上显示为一块网卡。这条链路有两个地址，板子的，以及板子告诉电脑去用的，而内核在创建 gadget 功能时把两个都随机生成，也就是每次启动。电脑按地址给这块网卡命名并记住它。在 Linux 上，这块网卡某天叫 `enxa61fb02c48c6`，第二天叫 `enx7605d4f0b702`，为其中一个配置的 IP 在另一个上就没有了。

它们是 configfs 里的两个文件：

```
/sys/kernel/config/usb_gadget/rockchip/functions/rndis.gs0/dev_addr
/sys/kernel/config/usb_gadget/rockchip/functions/rndis.gs0/host_addr
```

有两件事挡着，不能直接写。

**功能在使用中时内核会拒绝。** `sysdrv/source/kernel/drivers/usb/gadget/function/u_ether_configfs.h` 里的写入函数在 `opts->refcnt` 不为零时返回 `-EBUSY`，而只要有配置链接着这个功能，它就不为零。

**厂商的脚本没有钩子。** [`sysdrv/tools/board/android-tools/S50usbdevice`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/tools/board/android-tools/S50usbdevice) 一口气创建功能、建立链接、绑定控制器。

所以只能跟在它后面做，放在自己的一个启动脚本里，编号紧挨在它之后：

```sh
G=/sys/kernel/config/usb_gadget/rockchip
udc=$(cat $G/UDC)
echo none > $G/UDC                  # off the bus
rm $G/configs/b.1/f1                # whichever link points at rndis.gs0
echo "$dev"  > $G/functions/rndis.gs0/dev_addr
echo "$host" > $G/functions/rndis.gs0/host_addr
ln -s $G/functions/rndis.gs0 $G/configs/b.1/f1
ifconfig usb0 down; ifconfig usb0 hw ether "$dev"; ifconfig usb0 up
echo "$udc" > $G/UDC                # back on
```

`usb0` 已经带着旧地址存在了，得另外告诉它。电脑会看到板子离开又回来一次，间隔 0.4 秒，发生在启动后 5 秒。功能目录在厂商脚本重启之后仍然在，因为那个脚本开头是 `test -d ... || configfs_init`，所以拔掉线再插上，地址也不变。

这两个地址不需要存：在你的脚本运行之前没有任何东西读它们，重新算一遍也不花什么。

## 谁来分配 IP

`dhcpcd` 为每个网口运行，哪个口有了链路就去要地址。USB 网络另外还从厂商的 `S99usb0config` 那里得到一个固定的 `172.32.0.93`。厂商应用的启动脚本会为有线网口自己再启动一个 DHCP 客户端；如果你替换了那个启动脚本，把网口拉起来就够了。

## 检查

- 重启两次；地址相同，而且第二次启动时 `addr_assign_type` 是 0：它来自 U-Boot，不是你的脚本。
- 在电脑上用序列号把地址算出来，对比。
- 手工写入一个不带本地管理位的地址；重启之后它还在。
- 把整个镜像再刷一遍；地址不变，因为构建不为这个分区生成镜像。
- 在电脑上，USB 网卡每次启动之后都是同一个名字。

这五项都做过。没做的：接网线，所以没有任何一项是从路由器那一侧看到的；USB 网络在 Windows 和 macOS 上；以及 eMMC，那上面 vendor 存储是按扇区偏移而不是按分区名找的。
