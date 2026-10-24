# Adaptive time-lapse PTS

Last edited: 2026-10-24

The H.264 recording is a single continuous stream whose frame rate depends on
whether anything is moving. While the scene is still it is a time-lapse; while
something moves it plays back in real time. The switch is made by rewriting the
PTS of each frame before it reaches the encoder, in `h264_thread`
(`src/media.c`). This note explains why it is built that way and where it falls
short.

## The problem

The camera watches a scene that is still for hours and moves for seconds. A day
might be 23 hours of nothing and a few minutes of activity, scattered.

Conventional event-triggered recording handles this by starting a clip when
motion is detected and stopping after a timeout. That leaves three problems:

- Everything between events is gone. Slow changes that never trip the detector
  (light, an object that appears between two events) are not recorded at all.
- The beginning of an event is lost unless the recorder keeps a pre-roll buffer
  and splices it in, which means buffering encoded video in RAM and managing
  clip boundaries.
- The output is many short files, each with its own start and stop, that a
  player has to stitch together to show a day.

Recording continuously at a low frame rate solves the first and third problems
but makes the moving parts useless: at 1 fps, a person crossing the frame is two
or three stills.

The design here records the whole day as one stream, at a low rate while idle
and the full rate while moving, and presents the result to the encoder and the
HLS muxer as an ordinary constant-rate stream.

## Timeline model

The sensor runs at a fixed rate (`h264.fps`, 30). `h264_thread` keeps a subset
of the frames and assigns each kept frame a synthesized PTS:

| State | Frames kept | PTS advance per kept frame |
|---|---|---|
| Motion | `fps_high` per second of real time | real elapsed time since the previous kept frame |
| Idle | `fps_low` per second of real time | real elapsed time × `fps_low` / `fps_high` |
| First frame, or first frame after a switch | always | `1 / fps_high` (nominal step) |

In both states the PTS advances by roughly `1 / fps_high` per kept frame, so the
encoder and every consumer downstream see a stream at a constant `fps_high`.
The difference is how much real time each frame represents: one frame period
while moving, `fps_high / fps_low` frame periods while idle. With the shipped
configuration (`fps_high: 30`, `fps_low: 1`) an idle second of real time becomes
one frame, and idle periods play back 30 times faster than real time.

As an illustration of the arithmetic (not a measurement): a day of 23 idle hours
and 1 hour of motion plays back in about 23 h / 30 + 1 h ≈ 1 h 46 min.

Nothing downstream knows the stream is variable. The encoder sees frames at
`fps_high`, libhls cuts segments on keyframes and writes PTS-based durations,
and a browser plays the playlist as normal HLS. The MJPEG live preview is a
separate VI channel and is not affected; it is always real time.

## Why the hardware PTS, not a frame count

Both the keep decision and the PTS advance are computed from the frame's
hardware PTS (`stVFrame.u64PTS`), not from counting frames.

A frame count only equals time if the sensor delivers exactly its nominal rate
and no frame is lost on the way. Neither holds. The sensor can under-run (the
code comment cites 27 fps instead of 30), and `RK_MPI_VI_GetChnFrame` can time
out and skip. A count-based gate ("keep every 30th frame while idle") would then
keep fewer than `fps_low` frames per real second, and a count-based PTS would
make the stream's motion segments run faster than real time.

Using the hardware PTS makes the rules hold in terms of time: idle keeps
`fps_low` frames per real second whatever the sensor actually delivers, and a
motion segment's duration in the stream equals its duration on the wall.

## Keep gate: accumulator, not last + interval

The gate holds a deadline, `next_keep_hw`, and keeps the first frame whose
hardware PTS reaches it. After a keep, the deadline is advanced by one interval
from the *previous deadline*, not from the PTS of the frame just kept.

The difference matters because frames arrive on the sensor's grid, not the
gate's. With `fps_low = 1` and a 30 fps sensor, 30 sensor periods are 999 990 µs
(33 333 µs × 30), just short of the 1 000 000 µs interval. A gate of the form
"keep when `hw_pts >= last_kept + interval`" would therefore always wait for the
31st frame, keeping one frame every ~1.033 s instead of every 1 s. The error is
systematic: every keep is late by up to one sensor period, and the lateness is
never paid back.

With the accumulator the deadlines lie on a fixed grid. Each keep may still land
up to one sensor period after its deadline, but the next deadline does not
inherit that lateness, so the long-run average is exactly `target_fps`.

The accumulator has one escape: if the advanced deadline is already behind the
current frame (`next_keep_hw <= hw_pts`), it is re-anchored to
`hw_pts + interval`. Without this, after a long gap (a stalled `GetChnFrame`, or
a sensor running slower than `target_fps`) the deadline would trail far behind
and the gate would pass a burst of consecutive frames to "catch up".

TODO: was the last + interval form ever run here, and if so, was the effect seen
on the motion side as well (`fps_high` equal to the sensor rate, where the same
lateness would drop frames rather than delay them)? I have only derived the idle
case.

## Mode switches

When `motion_state` differs from the previous kept frame's state, two rules
apply.

**The first frame after a switch is always kept.** The deadline still in force
belongs to the old mode. Coming out of idle it can be up to `1 / fps_low` (one
second) in the future; honouring it would drop the first second of motion on top
of what detection latency already costs (see Limitations). Going into idle,
keeping the frame is harmless. The gate is re-anchored to the new mode's
interval from that frame.

**The PTS advances by one nominal step, `1 / fps_high`, and does not jump.** The
hardware time elapsed since the previous kept frame straddles the switch and
belongs to neither mode cleanly. Coming out of idle it can be close to a second.
Treated as real time, it would put a one-second hole in the stream: the decoder
would hold the last idle frame on screen for a second before motion starts.
Treated as idle time, the compression ratio would be applied to time that was
partly motion. Either choice also presents an irregular frame interval to the
encoder and the muxer. A nominal step keeps the stream at a constant `fps_high`
across the boundary.

The cost is that the real time spanned by the switching interval is not
represented in the stream: at most one idle interval (`1 / fps_low`) of wall
time per switch is collapsed into one frame period. This is one reason the
stream-to-wall-clock mapping below is only piecewise linear.

## CBR fixed at fps_high

The encoder runs CBR with `SrcFrameRate` set once at startup to `fps_high`
(`venc_set_framerate` in `media_init`) and never changed.

CBR divides the target bitrate among frames according to the declared source
frame rate. Because the rewritten PTS presents `fps_high` frames per stream
second in both modes, `fps_high` is the rate the rate control actually sees, and
it needs no retune at a switch.

Declaring a lower rate in idle was tried. The result, as recorded in the code
comment, was that idle segments grew by about 1.5× with no benefit: a lower
declared rate gives each frame a larger bit budget, which a near-static frame
does not need. Retuning per switch would also mean calling `SetChnAttr` on a
running channel at every transition, which conflicts with §6.7 of the VENC
guide.

TODO: details of the experiment for this section. What `SrcFrameRate` was
declared in idle (`fps_low`, or something else)? Was the 1.5× measured as .ts
size per segment, per hour, or bitrate? Was image quality compared, and on what
scene? Which document and version is "the VENC guide", and what does §6.7 say
exactly, so the reference can be checked?

A consequence of fixing the rate is that storage cost per *real* hour differs by
the compression ratio. At the shipped 4000 kbps, a stream second costs the same
in both modes, but an idle stream second covers 30 real seconds. Nominally that
is about 1.8 GB per hour of motion and about 60 MB per hour of idle (CBR
targets, not measured file sizes).

## Segments and the GOP

With `hls_duration_s: 0`, libhls cuts a segment at every keyframe, so a segment
is one GOP (`h264.gop: 60` frames). The open segment is buffered in RAM until it
is cut, so a power loss costs at most one segment (`storage.c`, `hls_create`).

Because the GOP is counted in frames, its real-time length depends on the mode.
At `fps_high = 30` a GOP is 2 s of stream time in both modes, but 2 s of real
time while moving and 60 s of real time while idle. The power-loss bound is
therefore one GOP of stream time, which during idle is up to a minute of the
real day.

## Limitations

**The stream-to-wall-clock mapping is not stored.** The mapping from stream time
to wall-clock time is piecewise linear: slope 1 during motion, slope
`fps_high / fps_low` during idle, with a break at every switch (plus the
collapsed interval at each break, described above). The daemon does not persist
this mapping. What it does record:

- `VideoSegments.start_time`: the wall-clock time a recording directory was
  opened.
- `VideoSegments.total_frames` and `EventDetails.motion_frame`: frame indices
  into that recording.

Turning a frame index or a stream position into a wall-clock time would require
the sequence of switches, which is not written anywhere. The only per-frame wall
clock in the recording is the OSD timestamp burned into the picture, which a
viewer can read but software cannot. Seeking to "14:32" in a day's recording is
therefore not possible as built.

Related, smaller effects: the storage writer reads `current_fps` (set by the IVS
thread) to classify each frame, while `h264_thread` reads `motion_state`
independently, so the two can disagree for a frame around a switch. And because
motion segments follow the hardware clock, a sensor that under-runs makes frame
index × `1 / fps_high` drift from stream time.

**The start of an event is lost, up to about a second.** Motion detection runs on
a separate VI path (the bypass sampling channel at `ivs.width × ivs.height`,
`ivs.fps`), analysed every `md_interval` frames and polled every `poll_ms`.
By the time `motion_state` flips, the full-resolution frames covering the onset
of motion have already been through the keep gate at `fps_low`, and all but one
per second were released. There is no pre-roll buffer, so they cannot be
recovered. The loss is bounded mainly by the idle interval, `1 / fps_low`, plus
the detection latency.

TODO: has the detection latency (motion onset to `motion START` in the log) been
measured? If so, the bound can be stated as a number rather than "about a
second".

**Quality wobbles briefly at a switch.** The first P-frame after an idle→motion
switch is predicted from the last idle frame, which may be up to a second old in
real time and, by definition, from before the motion began. The residual is
large while CBR still allots each frame `bitrate / fps_high`, so the first frames
of an event are under-budgeted until the encoder catches up or the next I-frame
arrives. The same applies more mildly to every idle frame, whose reference is
`1 / fps_low` older, which is normally fine for a still scene but not for a
gradual lighting change.

TODO: is this visible in practice, and for how long? I have derived it from the
encoder setup rather than seen it.

**There is no audio.** The pipeline has no audio input and the muxer only
receives `PSI_STREAM_H264`. The model allows one to be added: motion segments
are real time, so captured audio can be muxed against them directly. Idle
segments are compressed and real audio cannot be played back at 30× usefully;
they would be filled with silent frames covering the segment's stream duration,
so the audio track stays continuous for HLS.
