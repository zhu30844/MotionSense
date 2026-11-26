# Events and the recording database

Last edited: 2026-11-26

This is a design, agreed on 2026-11-25 and not built yet. It replaces the
databases the recorder writes today, which record frame numbers and cannot say
when anything happened. What exists today is described [at the end](#what-exists-today),
so the difference is clear. Where a number here was measured, it says so;
the rest is intent.

## How it is used

The footage is watched on a timeline. Stillness is not worth watching, so idle
stretches are a time-lapse and what happens in between plays at full speed;
the viewer sees what led up to a moment and what followed. An event is where
the timeline is worth watching.

A list of events is not planned. It needs nothing more than is stored here.
Events have no thumbnails: they are sparse, and the way to see one is to play
it.

## An event

An event is an interval of time with a kind. The only kind for now is motion.
Others will follow, such as a person or a sound; a knock or a bark is the same
thing with a short interval, and an instant is an interval whose start and end
are equal. Which kinds switch the recording to full rate is a rule in the
code, not something stored.

One decision sets both where an event begins and ends and when the frame rate
changes:

- Motion is detected: the event begins and the recording goes to full rate.
- Motion is detected again within the merge gap: the event goes on.
- No motion for the merge gap: the event ends and the recording goes back to
  time-lapse.

The merge gap is 5 seconds and configurable. It replaces
`ivs.motion_debounce_ms`, which is 1 second and only spaces out marks. Someone
standing still for an hour is not an event: it ends 5 seconds after they last
moved. Each event therefore ends with a few seconds of stillness at full rate,
which is the part that shows what followed.

Today the frame rate drops back on the first still frame, so an action is
recorded in pieces. Making the event and the frame rate one decision fixes
that: it is the "better switching" item on the roadmap.

### Interruptions

Midnight, a power loss and a restart all do the same thing: the event ends,
and if the motion is still going a new event begins.

- **Midnight.** The day changes at midnight whatever is happening. An action
  that crosses it is two events, one ending at 24:00 and one beginning at
  00:00, and is counted twice. That is accepted: it is rare, and it needs no
  rule of its own. A new day starts a new playlist, which has to begin on a
  keyframe, so the recorder asks the encoder for one at the change. Waiting
  for the next one, as the code does today, would lose up to two seconds in
  the middle of the action.
- **Power loss.** An event is written when it begins, without an end, and the
  end is filled in when it ends: two writes for each event. After a power loss
  the end is missing. At the next start the recorder fills it in with the
  point that recording actually reached, which the playlist gives.

## What is stored

Each day has a directory, named for the local date, with a database in it:

| Table | A row is | Holds |
|---|---|---|
| Recordings | One unbroken run of the recorder, which is one directory of segments | The directory, when it began |
| Events | One interval | Its recording, its kind, when it began and ended, where it begins and ends in the recording, optional data |

- **Times are UTC**, as milliseconds since 1970. The page converts them.
- **Where an event is in the recording** is what the timeline draws. Idle
  stretches are compressed thirty times, so a position on the progress bar is
  not a linear function of the time of day. Each event carries its own
  position, and nothing has to be converted.
- **Optional data** is text, empty for motion. It is for what a later kind
  needs to say, such as how sure a detection is.
- **Not stored**: frame numbers, frame counts and motion counts. They can be
  worked out, or nobody needs them.

One more database, beside the day directories, has a row for each day: the
date and whether the day is waiting to be deleted, so that the agent stops
serving a day before its files go. It also carries the version of the whole
tree.

## Versions

The tree has one version number. There is no migration and no reading of an
older layout. A recorder that finds a tree of another version renames `DCIM`
to `DCIM-v<number>` and starts an empty one. That is one rename: it cannot be
left half done by a power loss, and the old footage is still ordinary HLS that
a PC can play from the card.

Old trees stay until the user formats the card, and automatic cleanup never
touches them. A card that was nearly full when the version changed leaves
little room for new footage. So the status page says how much of the card old
versions hold, and offers to format it. A script on the board does the
formatting; the agent only asks for it.

## Summaries

The calendar's heat is the number of events in a day or the time they cover.
Both are worked out from the events table when asked for, a month at a time.
Which one is shown is the page's choice.

Nothing is cached. A cache would have to be dropped when a day is deleted,
when `DCIM` is renamed, and when the card is swapped or formatted, and a
missed case shows days that are not there. The memory would have been a few
kilobytes; the invalidation is the cost.

Measured on the Pro Max with today's databases: the calendar, which reads one
database, takes 8 ms; a whole day, with 3,400 marks and its playlist, about
135 ms; a nearly empty day 30 ms. A summary of one day should be near the
last figure, so a month should be under a second. That is an estimate until
the new tables exist. If it is too slow, the recorder writes a day's summary
once, when the day is over, into that day's row in the database beside the
directories. There it travels with the data and cannot go stale.

## Where things live

Decided with the above, because it says what may be put in these databases.

- **The SD card is neither secret nor trusted.** Whoever holds it can read
  everything on it, and what is on it may have been changed. It holds
  recordings and nothing else. It is not encrypted: the key would have to be
  on the board for it to record unattended, so encryption would only stop
  someone who takes the card and leaves the board, and the price is a card no
  PC can read and footage that dies with the board.
- **Secrets stay on the board**, in `/userdata`: the password's hash, sessions
  and, later, Wi-Fi credentials. Settings move there too; `config.json` is on
  the card today.
- **The agent reads the recording databases and never writes them.** The
  recorder is their only writer. The agent writes its own few files in
  `/userdata`, and still deletes nothing.
- **A login keeps out people on the network**, not people who can touch the
  board: they can pull the card or reflash it. That is said plainly here
  because the people being recorded are often the ones within reach.
- **A factory reset erases `/userdata`**, done by recovery because the running
  system cannot format what it has mounted. It is started by holding a button
  for some seconds, which is also the answer to a forgotten password. The
  BOOT button serves: tried on the Pro Max, the kernel reports it as key 115
  on `/dev/input/event0`, pressed and released, while the system runs. Held
  while power is applied it puts the chip in Maskrom mode instead, so the
  gesture is a long press on a running board.
- **The Ethernet address does not live in `/userdata`.** It is in Rockchip's
  vendor storage, the `vnvm` partition, which neither an update nor a factory
  reset touches; see *Partitions* in [BUILD.md](BUILD.md#partitions). It
  is worked out from the chip's serial number, so it comes back the same even
  after the whole flash is erased; an address that is not locally
  administered, which is one a factory wrote, is left alone.

## Not in this design

- Thumbnails, and a page listing events.
- Keeping an event from being cleaned up. It is wanted later. The direction is
  to copy that stretch of footage out to a directory of its own, which leaves
  the events table and cleanup by whole days as they are.
- A clock that is wrong at boot: events go under the wrong date.
- Encrypting footage. If it is ever wanted, the place to look first is HLS's
  own AES-128 for segments, which keeps the file system readable.

## What exists today

| Database | Holds |
|---|---|
| `VideoMetadata.db`, one | A row for each day: date, `motion_count`, `state` |
| `EventLogs.db`, one in each day's directory | `VideoSegments`: a row for each run of the recorder, with its directory, a time of day and a frame count. `EventDetails`: a row for each mark, with its run and a frame number |

- A mark is written about once a second while there is motion: 3,446 on
  2026-11-24. Marks have no beginning, no end and no time of day.
- `motion_count` is wrong on a day the recorder started more than once. The
  count starts from zero at each start and overwrites the day's row.
- The frame count is updated every second while recording, each a commit to
  the card. It only matters when a run ends.
- Times are local, without a zone, and the start of a run has no date.
- Nothing says which layout a database has.
