# Putting your own app in the Rockchip SDK's build

Last edited: 2026-11-26

Written by Claude, an AI model made by Anthropic, from work it did on this
project with its owner. Not reviewed by a person.

The Luckfox Pico SDK builds a whole image, with an application on top. The
application it expects is `rkipc`, Rockchip's camera program. This is how to
replace it with your own: how the SDK decides what to build, the places it
lets you in without changing its files, and the two traps behind "I removed
it, why is it still in the image".

Done on a Pico Pro Max, RV1106. Paths are in the SDK, linked to
[LuckfoxTECH/luckfox-pico](https://github.com/LuckfoxTECH/luckfox-pico).

## Method

**Add files; do not edit the vendor's.** Nearly everything below is a file of
your own that a variable in the board configuration points at. A fork that
only adds files merges upstream without conflicts, and what you changed can
be listed with one `git diff --stat`.

**Before removing something, find who puts it there.** Deleting a file from
the image is easy and wrong: it comes back, or the thing that wanted it
breaks in an odd place. Find the `Makefile` that installs it and make that
not run.

**Ask `make` what it would do.** A dry run shows what a setting builds
without building it. With the SDK's cross compiler on `PATH`:

```sh
cd project/app
make -n -C rkipc RK_APP_TYPE=SOMETHING
```

**Look at what was packed, not at what you meant to pack.** After a build,
list `output/out/oem/usr`. On the board, compare checksums with your source.

## Every directory with a Makefile is an app

[`project/app/Makefile`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/app/Makefile):

```make
app_src := $(wildcard ./*/Makefile ./component/fastboot_server/Makefile)
app_src := $(dir $(app_src))
all: $(pkg-build)
	$(foreach target,$(app_src),make -C $(target)||exit -1;)
```

Put a directory with a `Makefile` under `project/app`, a git submodule for
instance, and it is built. Nothing has to be registered anywhere.

Your `Makefile` includes `../Makefile.param`. It gives the cross compiler
(`RK_APP_CROSS`), where Rockchip's media libraries and headers are, and
`RK_APP_OUTPUT`, which is `project/app/out`. Every app installs there, with
the macro `MAROC_COPY_PKG_TO_APP_OUTPUT` from the same file, and
[`project/build.sh`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/build.sh)
takes it from there:

| Put it in | It ends up in | Copied by |
|---|---|---|
| `$(RK_APP_OUTPUT)/bin`, `lib`, `share` | `/oem/usr/bin`, `lib`, `share` | `__PACKAGE_RESOURCES` |
| `$(RK_APP_OUTPUT)/root` | The root file system, from `/` | `__PACKAGE_ROOTFS` |

So an init script goes in `root/etc/init.d`, and a program in `bin`.

Two details of `Makefile.param` cost us time. Its macros use bash syntax, so
set `SHELL := /bin/bash` in your `Makefile`; and it adds `-j` to `MAKEFLAGS`,
so targets with an order between them need it stated.

## RK_APP_TYPE picks the app

Every app is visited. Each builds only when the board configuration's
`RK_APP_TYPE` holds a name it knows. From
[`project/app/rkipc/Makefile`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/project/app/rkipc/Makefile):

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

No name matched, no target: `make` prints "build rkipc done" and has built
nothing. There is no list of valid names; each `Makefile` holds its own.

| App | Names it answers to |
|---|---|
| rkipc | `RKIPC_RV1106`, `RKIPC_RV1106_DUAL_IPC`, and a dozen more |
| uvc_app_tiny | `UVC_TINY` |
| wifi_app | `RK_WIFI_APP` |
| rk_smart_door | `SMART_DOOR_RV1106_RMSL` and three more |
| fastboot_client | `RK_FASTBOOT_CLIENT` |

What follows from that:

- **It is a list.** `filter` matches words, so two names build two apps.
- **Empty builds no app at all.** `build_app` in `build.sh` begins with
  `check_config RK_APP_TYPE || return 0`. Unset, it returns before `make`,
  and your own app is not built either.
- **A wrong name is not an error.** Nothing checks it. A typo builds nothing
  and the build reports success.
- **To leave the vendor's apps out, use a name none of them knows**, and have
  your own `Makefile` build only for that name, as theirs do:

```make
ifneq (, $(filter MYAPP, $(RK_APP_TYPE)))
all: my-targets
else
all:
	@echo "build myapp skipped"
endif
```

Leaving `rkipc` out also leaves out what it builds first,
`component/rkfsmk` and `component/third_libs`. If your app took a library
from there, it has to come from somewhere else; ours come from buildroot.

## RkLunch.sh is a socket

`__PACKAGE_OEM` in `build.sh` writes an init script, `S21appinit`, that does
one thing at boot:

```sh
sh /oem/usr/bin/RkLunch.sh
```

The SDK does not own that file. Each app installs its own: there are more
than a dozen in `project/app`, one beside each variant of each vendor app.
It is the SDK's socket for an app's start-up, not a part of `rkipc`. Install
one from your app's `bin` and it is yours.

Before writing yours, read the one you are replacing, here
`project/app/rkipc/rkipc/src/rv1106_ipc/RkLunch.sh`, and sort what it does
into what you need and what you do not:

| It does | Needed without rkipc |
|---|---|
| Calls `insmod_ko.sh` to load the camera's kernel modules | Yes |
| Saves and restores the Ethernet address in `/userdata/ethaddr.txt` | No: see [the network post](network-identity.md) |
| Starts a DHCP client on the wired port | No: `dhcpcd` already runs |
| Makes links for rkipc's web pages | No |
| Picks an rkipc configuration by sensor | No |
| Plays a test sound | No |
| Starts rkipc | No |

The same init script runs `sh /oem/usr/bin/RkLunch-stop.sh` at shutdown.
Nothing depends on it; without the file that `sh` has nothing to open, which
we read from the script and did not watch happen.

## Keep insmod_ko.sh

[`sysdrv/drv_ko/insmod_ko.sh`](https://github.com/LuckfoxTECH/luckfox-pico/blob/main/sysdrv/drv_ko/insmod_ko.sh)
is crude, one `insmod` after another, each skipped if the file is missing.
Call it; do not rewrite it. It knows three things that change with the SDK:

- **The order**, which is the dependency order, worked out by hand.
- **The sensor is unknown.** It loads every sensor driver, lets each probe
  the bus, then unloads those nothing is using:

```sh
__insmod imx415.ko
__insmod sc3336.ko
...
__rmmod_camera_sensor
```

- **A parameter that depends on the sensor.** The last module is loaded with
  the sensor's height, read back from the ISP, and the address of a firmware
  file:

```sh
__insmod rockit.ko mcu_fw_path="./hpmcu_wrap.bin" mcu_fw_addr=0xff6fe000 isp_max_h=$sensor_height
```

It has no side effects, which is what sets it apart from the start-up script
above. It ends by running `insmod_wifi.sh`, which may not exist: one error at
each boot, harmless.

## Trap one: the order of the apps

The apps build in the order `wildcard` returns, which is alphabetical, and
each copies its files into `project/app/out` as it finishes:

```
fastboot_client  ipcweb  rk_smart_door  rkipc  uvc_app_tiny  wifi_app
```

Your directory takes its place among these by its name. When two apps
install a file of the same name, the later one wins, and `rkipc` is late in
the alphabet: ours began with `m` and lost. "Install mine too and let it
overwrite" works only if your directory sorts after the vendor's, and that
is not something to depend on. Make the other app not build.

## Trap two: two directories that never empty

Change `RK_APP_TYPE`, build, and the image still has rkipc's files. Rkipc
was not built. The files are from an earlier build.

| Directory | Is | Emptied by |
|---|---|---|
| `project/app/out` | Where apps install | `./build.sh clean app` |
| `output/out/oem` | Where the `oem` partition is put together | Nothing: delete it by hand |

`__PACKAGE_OEM` only ever copies into the second. `build_clean` has cases for
`uboot`, `kernel`, `rootfs`, `driver`, `sysdrv`, `media`, `app`, `recovery`
and `all`, and none for it short of `all`.

We emptied the first, built, and still found a stop script, a font and two
libraries from rkipc in the image. Deleting the second removed them. So after
dropping a file from what an app installs:

```sh
./build.sh clean app
rm -rf output/out/oem
./build.sh
```

A build server starts from an empty tree and never sees this, so a release
can be right while the board on your desk is wrong.

## Where the SDK lets you in

| To change | Add | Named by |
|---|---|---|
| The partition table | A line in your board configuration | `RK_PARTITION_CMD_IN_ENV` |
| What is deleted from `oem` before packing | A script beside the board configuration | `RK_PRE_BUILD_OEM_SCRIPT` |
| Kernel options | A fragment in `arch/arm/configs` | `RK_KERNEL_DEFCONFIG_FRAGMENT` |
| U-Boot options | A fragment in U-Boot's `configs` | `RK_UBOOT_DEFCONFIG_FRAGMENT`, a list |
| The device tree | A `.dts` of your own | `RK_KERNEL_DTS` |
| Files in the root file system | An overlay directory beside the board configuration | `RK_POST_OVERLAY`, a list |
| Start-up | `RkLunch.sh`, from your app | Its name |
| An init script | A file in `$(RK_APP_OUTPUT)/root/etc/init.d` | Its number |

A board configuration of your own is a directory under `project/cfg`. It is
not in `./build.sh lunch`'s numbered menu, which is written out in
`build.sh`; choose the last entry, `custom`.

Where there is no way in, go around. The script that sets up the USB gadget
has no hook, so an init script numbered just after it redoes the one part
that matters.

## Where we did edit vendor files

For honesty about the method. In `build.sh`, one hook so that recovery can
run a script named by the board configuration. In `sysdrv/Makefile` and one
buildroot configuration, under twenty lines. Everything else in the fork is
added files.

## Checks

- `make -n` for each vendor app with your `RK_APP_TYPE`: one `echo` each.
- `ls output/out/oem/usr/bin output/out/oem/usr/share` after a clean build:
  nothing you do not recognise.
- On the board, `md5sum /oem/usr/bin/RkLunch.sh` against your source.
- `lsmod` lists the same modules as before the change.

All four were done on the Pro Max. Not done: the board configuration for a
second board was changed the same way and has not been built.
