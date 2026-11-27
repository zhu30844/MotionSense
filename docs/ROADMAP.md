# Roadmap

Last edited: 2026-11-27

1.x assumes one board, one SD card, fixed paths, two unsupervised processes
and hand-written pages. 2.0 replaces those assumptions; most features come
after it, each as a module on the new structure. Fixes for 1.x go on the `1.x`
branch.

## 2.0 milestone

2.0 has no migration from 1.x: upgrading means reflashing the image and
wiping the whole SD card. Recordings and configuration on it are not kept.

2.0 is for the Luckfox Pico Pro Max. The Pico Ultra comes
[after it](#luckfox-pico-ultra).

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

### Processes
- [x] A process that exits is started again
- [x] Watchdog, fed by the recording process only: a hung page or agent is
      not a reason to reset the board

### Updates
- [x] A partition table with `misc`, `recovery` and a `userdata` that holds an
      update package, in place before 2.0 ships: changing it later means
      another reflash. See *Partitions* in [BUILD.md](BUILD.md#partitions)
- [x] Updating through recovery: an uploaded package is flashed after a
      reboot, and a flash interrupted by a power loss starts over. See
      *Updates* in [BUILD.md](BUILD.md#updates)
- [ ] A login before the update endpoint is offered to users: today anyone
      who can reach the agent can flash the board
- [x] The version in `/api/status` and on the status page: it tells whether
      an update took
- [ ] An update page

### Front end
- [ ] A redesigned front end on Vue and Vite
- [ ] The same functions as the current pages
- [ ] A log page, which also shows safe mode and the count of bad boots
- [x] The agent's routes are in the namespaces of [API.md](API.md). Three of
      its field rules are still broken:
- [ ] `/api/status` drops the formatted fields (`cpuTemp`, `systemUptime`,
      `lastRecord`, …): they go with the hand-written pages that read them
- [ ] Times from the recordings endpoints are RFC 3339: `startTime` is a time
      of day today
- [ ] `state` in `/api/recordings/calendar` says what it means, not a number
- [x] The live picture is H264 over WebRTC (replaces MJPEG): the agent
      answers an offer at `POST /api/stream`
- [x] A live view that plays it in a `<video>`, on the Vue pages under
      `/v2/` and on the hand-written pages

### Recording
- [ ] Events as intervals, replacing the marks the databases hold today. The
      design is [events.md](events.md)
- [ ] Better switching between motion and stillness, so an action is recorded
      whole: today the frame rate drops back as soon as one still frame is
      reported (see *Known issues* in the [README](../README.md)). It is the
      same decision as where an event ends
- [ ] Settings and secrets on the board, not on the card; a factory reset
      that erases them, started by holding a button

### Development
- [x] PC simulator, so front-end work needs no board
- [x] Full-stack development environment (Node.js in the devcontainer)
- [x] The simulator runs without the board's fixed directories

## After 2.0

### Luckfox Pico Ultra

Target date: TBD.

Moved out of 2.0 on 2026-11-27. The Pro Max is reached over USB, from a phone
as well as a computer, which covers how the footage is watched; and audio,
which the Ultra has and the Pro Max does not, has no use for now.

- Board configuration, including the rule that mounts its external storage
- Updates: eMMC, and its own board file
- CI releases both boards in parallel
- Audio. The recording database is designed with room for it and nothing of
  it is built: see *Not in this design* in [events.md](events.md#not-in-this-design)

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
- Authentication
- OTA

### The network button: a provisional plan

Talked through on 2026-11-27. None of it is built and it may change.

- Pressing the network button opens a Wi-Fi access point for ten minutes. It
  closes when the time is up and nobody is connected.
- Only the camera can be reached through it: the board hands out addresses
  with no router and no DNS server and forwards nothing, as it does on the
  USB network. Someone in the house who does not have the router's password
  can watch, and can reach nothing else.
- The password is a default for each device, printed on its label, the way
  routers do it.
- The OLED shows a QR code that joins the access point, with its name beside
  it. Tried on the 0.96 inch SSD1306 with one phone: a code of 29 by 29
  modules, 2 pixels each with 3 pixels around it, for a 16-character name and
  a password, scans.
- Ethernet stays a DHCP client. Ethernet straight to a computer is what the
  USB network is for.
- Setting up the home Wi-Fi through the same access point is wanted and put
  off.
- It waits for the Wi-Fi card. Whether the card's driver can run an access
  point has not been checked, and the image has no program for one.

### Other
- Trim the image further: kernel modules for hardware the board does not have
