# 第三方组件

[English](THIRD-PARTY.md) | 简体中文

最后编辑：2026-10-24

`../LICENSE`（MIT）适用于为本项目编写的代码。本文列出源码树中的其他所有内容及其所附带的条款。路径相对于仓库根目录，而不是本目录。

## 适用 LICENSE（MIT）

| 路径 | |
|---|---|
| `src/`、`include/` | C 守护进程 |
| `agent/` | Go agent 及其 Web 资源，`agent/static/js/video-js-*/` 除外 |
| `cmake/`、`scripts/`、`Makefile`、`CMakeLists.txt` | 构建 |
| `config.yaml`、`S99motionsense`、`*.sh`、`docs/` | 打包与文档 |

## 在此分发，适用其各自的条款

| 路径 | 所有者 | 许可证 |
|---|---|---|
| `3rdparty/osd/*.c`、`*.h` | Rockchip Electronics Co., Ltd. | 3-clause BSD — `3rdparty/osd/LICENSE` |
| `3rdparty/osd/DejaVuSansMono.ttf` | Bitstream, Inc.; DejaVu and Arev authors | Bitstream Vera + Arev — `3rdparty/osd/DejaVuSansMono.LICENSE` |
| `agent/static/js/video-js-8.20.0/` | Brightcove / Video.js authors | Apache-2.0 |

OSD 源文件在每个头部都引用了其许可证文件；该文件即 `3rdparty/osd/LICENSE`。

OSD 字体为 DejaVu Sans Mono，替换了 SDK 自带的字体。OSD 只绘制 ASCII 时间戳。

## 仅引用，不分发

| 路径 | 所有者 | 获取方式 |
|---|---|---|
| `3rdparty/media-server/` | ireader | MIT。子模块，固定在 `ea53ac6`。`3rdparty/media-server-local/hls-media.c` 是其中的一个文件，带有一处本地修复，适用相同条款。 |
| `vendor/` | Rockchip Electronics Co., Ltd. | 不在本仓库中。由 `scripts/sync-vendor.sh` 创建，该脚本从 Luckfox SDK 检出目录中提取它。 |

## vendor/

`vendor/` 存放 Rockchip 的预编译 `librockit`、`librkaiq`、`librockchip_mpp` 和 `librga`，以及 462 个头文件，带有 `Copyright (c) 2021 Fuzhou Rockchip Electronics Co., Ltd`。

头文件中写明了各自的条款。`librockit` 和 ISP 头文件以 SPDX 行 `GPL-2.0 WITH Linux-syscall-note OR Apache 2.0` 开头；`librkaiq`、`librockchip_mpp` 和 `librga` 完整转载了 Apache-2.0 声明。两种选择都允许以二进制形式再分发，这正是由本项目构建出的可烧录镜像得以分发的依据，前提是这些声明随镜像一同提供。

适用的条款是随这些二进制文件一同提供的条款，而不是公开上游的条款，因为 SDK 提供的并不是上游构建：`media/mpp` 记录的提交不在 `rockchip-linux/mpp` 中，`media/rga` 记录的提交也不在 `airockchip/librga` 中。两者都是 Rockchip 内部构建，其许可证随头文件一同提供。

只有独立构建才需要它。SDK 应用构建通过 `MS_RK_MEDIA_DIR` 读取 SDK 自己的副本。

填充方法：

```bash
./scripts/sync-vendor.sh            # or: ./scripts/sync-vendor.sh <sdk-path>
```

该脚本读取 SDK 中的 `media/`，这些库在那里以源码形式提供，因此普通的 SDK 克隆即可，无需构建 SDK。

## 免责声明

本清单记录的是文件本身所声明的内容。它不构成法律意见。

---

由 Claude（Opus 5）根据 SDK 源码及在 Luckfox Pico Pro Max 上的测试撰写。由 ZIXUAN ZHU 审阅。
