# Roadmap

Last edited: 2026-11-22

1.x assumes one board, one SD card, fixed paths, two unsupervised processes
and hand-written pages. 2.0 replaces those assumptions; most features come
after it, each as a module on the new structure. Fixes for 1.x go on the `1.x`
branch.

## 2.0 milestone

2.0 has no migration from 1.x: upgrading means reflashing the image and
wiping the whole SD card. Recordings and configuration on it are not kept.

### Boards
- [x] A read-only board file in the image that states what the board has
      (replaces board detection). The user's `config.json` stays separate: it
      says what the user wants, the board file says what is there.
- [ ] Modules start according to the board file and the user's configuration
- [x] The board file and the user's configuration are both JSON (replaces
      `config.yaml`): programs will write the configuration once there is a
      settings page, and JSON survives that unchanged
- [x] The storage location comes from the board file (replaces the fixed
      mount point), so an SD card and a USB drive are the same to the programs
- [x] Recording checks that storage is mounted before writing, so a missing
      card never sends recordings to flash
- [ ] Board configuration for the Luckfox Pico Ultra, including the rule that
      mounts its external storage

### Processes
- [x] A process that exits is started again
- [x] Watchdog, fed by the recording process only: a hung page or agent is
      not a reason to reset the board

### Updates
- [ ] A partition table with two slots, settled before 2.0 ships: changing it
      later means another reflash. See *Partitions* in
      [BUILD.md](BUILD.md#partitions)
- [ ] U-Boot picks a slot and falls back when the new one does not come up

### Front end
- [ ] A redesigned front end on Vue and Vite
- [ ] The same functions as the current pages
- [ ] A log page, which also shows safe mode and the count of bad boots
- [ ] The agent's routes follow [API.md](API.md)

### Recording
- [ ] Better switching between motion and stillness, so an action is recorded
      whole: today the frame rate drops back as soon as one still frame is
      reported (see *Known issues* in the [README](../README.md))

### Development
- [x] PC simulator, so front-end work needs no board
- [x] Full-stack development environment (Node.js in the devcontainer)
- [x] The simulator runs without the board's fixed directories
- [ ] CI releases both boards in parallel

## After 2.0

### Features
- Peripherals
  - The 4-inch screen, as a process of its own, woken by motion
  - OLED
  - Temperature and humidity
  - Servo
  - Microphone
  - Speaker (prompt and greeting sounds, alarm)
- Network
  - No more fixed IP address; simpler set-up
  - Access over Wi-Fi (as a client or an access point) or Ethernet
  - Access over the USB network
- Basic AI on the NPU (YOLO and the like)
  - Person detection
- Ambient light compensation, or an alternative, so lighting changes do not
  trigger recording
- Better live view (WebRTC)
- Authentication
- OTA

### Other
- Trim the image further and remove rkipc completely
