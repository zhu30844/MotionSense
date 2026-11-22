# MotionSense 网页前端

[English](README.md) | 简体中文

最后编辑：2026-11-22

Vue 3、TypeScript 和 Vite。它将取代 `agent/static` 里手写的页面；在那之前，它和旧页面并存，挂在 `/v2/` 下。

## 开发

Node.js 已包含在 SDK 的 devcontainer 里。

```bash
npm install          # once
npm run dev          # http://localhost:5173/v2/
```

保存文件后浏览器里即时更新，不用刷新。开发服务器只提供页面；`/api` 会被转发给一个 agent，它需要在运行：

```bash
../../scripts/pcsim.sh                       # the simulator, on port 3000
MS_AGENT=http://172.32.0.93 npm run dev      # or a board instead
```

如果页面不再跟随你的修改，见 SDK README 里关于 inotify 监视上限的说明。

## 构建

```bash
npm run build        # type-check, then write ../static/v2
```

agent 嵌入的是 `agent/static`，所以下一次构建 agent 后就能在 `/v2/` 访问到。构建产物不进仓库，目前也没有任何流程会自动构建它：没有它时构建出的 agent 就没有 `/v2/`。

## 检查

```bash
npm run lint         # ESLint, fixing what it can
npm run format       # Prettier over src/
```

## 说明

- 路由使用 hash 网址（`/v2/#/…`）：agent 只提供文件，没有回退到 `index.html` 的逻辑。
- 这里的 `go.mod` 不含 Go 代码。它把这个目录标记为另一个模块，让 go 工具不进入 `node_modules`。
