# MotionSense

English | [简体中文](README_cn.md)

Last edited: 2026-11-19

Motion-triggered video recording for the Luckfox Pico Pro Max (Rockchip
RV1106). Records H.264 to HLS on the SD card, serves a live MJPEG stream and a
playback UI over HTTP, and logs motion events to SQLite.

## What it is for

Originally written for a shared fridge — who took what. It may suit other
scenes of the same shape, static for hours with a few seconds of activity: a
dorm room, a store cupboard, a warehouse aisle.

- **Get through a whole day fast.** Idle stretches play back sped up, with no
  scrubbing back and forth.
- **See the moment at full speed.** Motion is recorded and played at the high
  rate.
- **Save storage.** Idle time is recorded at one frame per second, so a day of
  footage stays small.
- **See where the activity was.** Every switch to the high rate leaves a mark
  on the seek bar.

## Screenshots

Live view, with the OSD timestamp and the device status bar:

![Live view](docs/img/Screenshot%20From%202026-09-05%2012-52-56.png)

History: a calendar of the days with footage, coloured by how much motion each
day had:

![Motion calendar](docs/img/Screenshot%20From%202026-09-05%2012-19-39.png)

Playback of one day. The red marks on the seek bar are the switches to the
high rate:

![Playback](docs/img/Screenshot%20From%202026-09-05%2012-20-03.png)

## Features

- **Adaptive frame rate.** Records at 1 fps while idle and about 30 fps while motion
  is detected. Thresholds, sensitivity and night mode are configurable.
- **HLS recording.** One `.ts` per keyframe by default, organised into
  date-based directories with a per-day event database and automatic cleanup
  when free space runs low.
- **Live view and playback.** MJPEG stream at `/api/stream`, recordings
  browsable by date, plus a `/api/status` endpoint reporting uptime, memory,
  load, SoC temperature and the last day with footage.
- **OSD timestamp** burned into both the recording and the live stream.

## Requirements

- Luckfox Pico Pro Max, SPI NAND boot
- An SD card, **ext4**. It must not carry the `orphan_file` feature — the 5.10
  kernel cannot mount that read-write. See
  [docs/BUILD.md](docs/BUILD.md#the-sd-card).
- Enough card for the footage you want to keep. Below
  `storage.disk_free_min_mb`, 2 GB by default, the oldest day is deleted to
  make room; recording itself never stops.
- x86-64 Linux host

## Usage

1. **Flash the image.** Download the latest image and flash it to the onboard
   SPI NAND with the full one-click flash, not to the SD card. The Luckfox wiki
   covers how: [Getting Started](https://wiki.luckfox.com/Luckfox-Pico-RV1106/Getting-Started/Pico-Pro-Max/).
2. **Format the SD card as ext4.** On Windows, [DiskGenius](https://www.diskgenius.com/)
   can do it; on Linux, use the commands below.

   Check the version first with `mke2fs -V`. On 1.47 or later, run them as
   they are. Below 1.47 (Ubuntu 22.04 ships 1.46.5), drop `-O ^orphan_file`
   from step 4 of the commands, or it fails with `Invalid filesystem option
   set`; older versions never enable the feature anyway.

   ```bash
   # 1. Find the card first; do not pick the wrong disk
   lsblk -o NAME,SIZE,MODEL,MOUNTPOINTS

   # 2. Unmount any mounted partitions on the card
   sudo umount /dev/sdX?*

   # 3. Repartition: MBR, one partition across the whole card
   sudo parted -s /dev/sdX mklabel msdos mkpart primary ext4 1MiB 100%

   # 4. Format as ext4 without orphan_file
   sudo mkfs.ext4 -O ^orphan_file -m 0 -L MOTIONSENSE /dev/sdX1

   # 5. Check: orphan_file must not be in the output
   sudo dumpe2fs -h /dev/sdX1 | grep -i features
   ```

3. **Power up.** Insert the SD card and the camera, connect the network and
   power the board. It starts recording on boot with nothing to configure.
4. **Open the web page.** Browse to `http://<board IP>/` for the live view and
   playback. The address depends on how the board is connected:
   - **Ethernet to a router**: the board gets its address over DHCP. Find it in
     the router's device list, or with `adb shell ifconfig eth0`.
   - **USB to a computer**: the board's USB network interface is fixed at
     `172.32.0.93`. Set the new interface on the computer to `172.32.0.100`,
     netmask `255.255.0.0`, and open `http://172.32.0.93/`.
   - **Ethernet straight to a computer**: nothing hands out addresses, so both
     ends need one set by hand. See [Offline communication](https://wiki.luckfox.com/Luckfox-Pico-RV1106/Ethernet-Config/#1-offline-communication)
     on the Luckfox wiki.

## How it fits together

Two processes, split by what each language is good at:

- **`MotionSense`**, in C, owns the pipeline — ISP, encoder and IVS motion
  detection through Rockchip's rockit, writing HLS and the metadata databases
  to the card. Nothing sits between it and the hardware.
- **`motionsense-agent`**, in Go, owns the network — HTTP, the UI, the API. It
  never touches rockit, so **no cgo**: a static binary built with
  `CGO_ENABLED=0`, reading the databases through `modernc.org/sqlite` in pure
  Go. It serves on port 80 as root, 3000 otherwise.

They talk over a unix socket (`/tmp/motionsense-stream.sock`), which keeps the
split honest: the daemon can die without taking the web interface with it, and
the agent restarts without disturbing a recording.

Configuration is one `config.yaml` on the SD card, seeded from the image on
first boot and never overwritten after that. Compiled-in defaults apply when
it is missing, so a blank card still records.

`S99motionsense` starts both, waits for the card to mount, and hands the
camera over from the stock `rkipc` app. It ships in the image through the
board overlay, so a flashed board records from first boot with nothing to
install and nothing to configure.

## Building

This is an application inside the Luckfox SDK, integrated the Rockchip SDK way
at `project/app/motionsense`. The SDK fork below carries the board
configuration, the device tree and the development environment; clone the
whole SDK:

**<https://github.com/zhu30844/luckfox-pico-sdk>**

```bash
git clone --recurse-submodules git@github.com:zhu30844/luckfox-pico-sdk.git
cd luckfox-pico-sdk
./build.sh lunch     # hardware "custom" -> MotionSense_Pro_Max
./build.sh
adb reboot loader                       # put the board in maskrom/loader mode
./rkflash.sh update
```

### Development container

The devcontainer is in the **SDK fork**, not in this repository — open
`luckfox-pico-sdk` in VS Code, not `MotionSense`. VS Code will offer *Reopen in
Container*; the image carries the cross toolchain, Go, and the build
dependencies, with `LF_SDK`, `LF_TOOLCHAIN` and `LF_SYSROOT` already set.

Editing this app means editing `project/app/motionsense` inside that workspace.
Building on the host works too — `./build.sh` puts the toolchain on `PATH`
itself — provided the SDK's build dependencies are installed.

[docs/BUILD.md](docs/BUILD.md) covers the build chain, the board configuration, the
on-device layout and what to check when something does not come up.
[docs/DEVNOTES.md](docs/DEVNOTES.md) covers working on the board: how to connect to it,
what to do when a link drops, and the bugs that present as something else.

## Known issues

- Switching between views raises the client count. Above about five clients
  the agent stops responding for a while.
- Motion has no hold window: the frame rate returns to 1 fps as soon as a
  still frame is reported. Events are typically under a second, so the end of
  an action can be recorded at the idle rate.
- Daylight saving is not honoured. Only the standard-time half of `/etc/TZ` is
  read, so a zone with DST is an hour out for half the year.

## Planned

### Features (mainly for the Pico Pro Max)
- Peripherals
  - OLED
  - Temperature and humidity
  - Servo
- Basic AI on the NPU (YOLO and the like)
  - Person detection
- Ambient light compensation, or an alternative, so lighting changes do not
  trigger recording
- A better front end (a lightweight web framework)
- Better live view (WebRTC)
- Authentication
- OTA
- Watchdog

### Board support
- Multiple boards
  - Board detection
  - Update the mount points
- Luckfox Pico Ultra
  - Wi-Fi / multiple networks
  - The 4-inch screen
  - Microphone
  - Speaker

### Other
- A full-stack development environment
- Slim the image further and remove rkipc entirely

## Scope

A learning project. Not built, tested or reviewed as a security product, and
not suitable for one.

Concretely, on the image this repository produces:

- The HTTP interface has no authentication. Anyone who can reach port 80 can
  watch the live stream and every recording.
- The root password is the default, `luckfox`.
- Recordings and the metadata databases are unencrypted on the SD card.
- Nothing here has had a security review.

Use it only on a LAN you control. Do not expose it to the internet.

The author accepts no responsibility.

## Licence

MIT — see [LICENSE](LICENSE). [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md) lists everything
in the tree that is not covered by it.
