# MotionSense web front end

Last edited: 2026-11-22

Vue 3, TypeScript and Vite. It will replace the hand-written pages in
`agent/static`; until then it is served beside them under `/v2/`.

## Developing

Node.js comes with the SDK devcontainer.

```bash
npm install          # once
npm run dev          # http://localhost:5173/v2/
```

A saved file shows in the browser without a reload. The dev server serves the
pages only; `/api` is proxied to an agent, which has to be running:

```bash
../../scripts/pcsim.sh                       # the simulator, on port 3000
MS_AGENT=http://172.32.0.93 npm run dev      # or a board instead
```

`../../ms sim` starts the simulator and the dev server together.

If a page stops following your edits, see the note on inotify watches in the
SDK README.

## Building

```bash
npm run build        # type-check, then write ../static/v2
```

The agent embeds `agent/static`, so the next agent build serves the result at
`/v2/`. The output is not tracked. Everything that builds the agent runs
`scripts/build-web.sh` first: the SDK build, `scripts/pcsim.sh` and
`ms deploy`. A bare `go build` does not, and embeds whatever is there.

## Checks

```bash
npm run lint         # ESLint, fixing what it can
npm run format       # Prettier over src/
```

## Notes

- Routes use hash URLs (`/v2/#/…`): the agent serves files and has no fallback
  to `index.html`.
- `go.mod` here holds no Go code. It marks this directory as another module so
  the go tool stays out of `node_modules`.
