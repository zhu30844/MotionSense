# The agent's URLs

Last edited: 2026-11-22

What the agent serves, and the rules a new route or field follows. The routes
are registered in `agent/internal/server/server.go`.

## Three namespaces

| Prefix | Holds |
|---|---|
| `/api/` | Endpoints: JSON, or a stream |
| `/media/` | Recordings, as files |
| anything else | Pages |

They do not overlap, so a page route can never collide with an endpoint, and
"neither `/api/` nor `/media/`" is the whole rule for what is a page.

## Routes

| Route | Returns |
|---|---|
| `GET /api/status` | Device and recording status |
| `/api/stream` | The live picture, MJPEG |
| `GET /api/recordings/calendar` | The days that have footage |
| `GET /api/recordings/{date}` | One day's segments and motion marks |
| `GET /media/{date}/{segment}/{file}` | A playlist or a `.ts` |

## Pages

The Vue pages are one application with hash routes, `/#/…`: the agent serves
files and has no fallback to `index.html`. Until they replace the hand-written
pages they sit under `/v2/`. A page is named for what it does, and what it
shows goes in the URL so that it can be bookmarked: `/#/playback/2026-11-22`.

## Endpoints

- A resource is a plural noun, and what is inside it comes after:
  `/api/recordings/{date}`.
- `GET` reads and `PUT` replaces. Settings, when they come, are
  `GET /api/config` and `PUT /api/config`.
- No version in the path. The pages and the agent are one binary and cannot
  be out of step. This is to be looked at again when something outside that
  binary calls the agent, such as the screen process on the Ultra.

## Fields

- camelCase.
- Raw values, with the unit in the name: `uptimeSeconds`, `memTotalBytes`,
  `socTempCelsius`. The page formats them; an endpoint that sends `"55.3°C"`
  has decided how every reader displays it and stopped them comparing it.
- Dates are `YYYY-MM-DD`, times are RFC 3339.
- What the board cannot tell is `null`, not `""` and not `0`.

`/api/status` still sends an older set beside these (`systemUptime`,
`cpuTemp`, `lastRecord`, …) for the hand-written pages. They go when those
pages do.

## Errors

An HTTP status that says what happened, with a short text body. That is what
the current handlers send. A JSON body is worth having once a page needs to
tell errors apart.

## Not shown

The load average. It reads about 10 on an idle board: ten threads of the
vendor media stack sleep uninterruptibly while waiting for work and each
counts as 1.0. `cpuUsagePercent` and `npuUsagePercent` say what it was meant
to.
