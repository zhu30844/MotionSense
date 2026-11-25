# agent 的网址

[English](API.md) | 简体中文

最后编辑：2026-11-25

agent 提供哪些路径，以及新增路径或字段时遵循的规则。路径注册在 `agent/internal/server/server.go` 里。

## 三个命名空间

| 前缀 | 内容 |
|---|---|
| `/api/` | 接口：JSON 或数据流 |
| `/media/` | 录像文件 |
| 其余 | 页面 |

三者互不重叠，所以页面路由不会和接口撞名，"既不是 `/api/` 也不是 `/media/`"就是判断页面的全部规则。

## 路径

| 路径 | 返回 |
|---|---|
| `GET /api/status` | 设备和录制状态 |
| `POST /api/stream` | 请求体是 WebRTC 的 offer，返回 answer；实时画面随后以 H264 经 WebRTC 送达 |
| `GET /api/recordings/calendar` | 有录像的日期 |
| `GET /api/recordings/{date}` | 某一天的分段和运动标记 |
| `PUT /api/update` | 请求体是升级包；返回 202，随后板子重启并刷入 |
| `GET /media/{date}/{segment}/{file}` | 播放列表或 `.ts` |

## 页面

Vue 页面是一个应用，使用 hash 路由 `/#/…`：agent 只提供文件，没有回退到 `index.html` 的逻辑。在取代手写页面之前，它们挂在 `/v2/` 下。页面按功能命名，显示的内容写进网址，这样可以收藏：`/#/playback/2026-11-22`。

## 接口

- 资源用复数名词，里面的内容跟在后面：`/api/recordings/{date}`。
- `GET` 读取，`PUT` 替换。将来的设置就是 `GET /api/config` 和 `PUT /api/config`。
- 路径里不带版本号。页面和 agent 编在同一个程序里，不可能不同步。等这个程序之外的东西要调用 agent 时再重新考虑，比如 Ultra 上的屏幕进程。
- `PUT /api/update` 替换整个系统。请求体就是 tar 本身，不是表单。被拒绝的升级包得到 422，原因以文本返回；409 表示已有升级在进行，501 表示这是模拟器。它没有认证：见 [BUILD_cn.md](BUILD_cn.md#升级) 的*升级*一节。
- `POST /api/stream` 接入一个观看者。请求体是浏览器的 SDP offer 文本，响应是 201 和 agent 的 answer，里面已经带齐板子所有可达的地址：一来一回就结束，没有后续消息。400 表示 agent 读不懂这个 offer，503 表示已有四个观看者。画面本身不经过这个服务器：它从 agent 经 UDP 直接到浏览器。
- agent 从不删除文件。需要删除的东西由板子上的脚本删除。

## 字段

- 驼峰命名。
- 给原始数值，单位写在名字里：`uptimeSeconds`、`memTotalBytes`、`socTempCelsius`。格式由页面决定；接口如果返回 `"55.3°C"`，就替所有读者决定了显示方式，也让他们没法做比较。
- 日期是 `YYYY-MM-DD`，时间是 RFC 3339。
- 板子无法得知的值是 `null`，不是 `""` 也不是 `0`。

`/api/status` 目前还附带一组旧字段（`systemUptime`、`cpuTemp`、`lastRecord` 等），供手写页面使用。它们随那些页面一起移除。

## 错误

用能说明情况的 HTTP 状态码，加一段简短的文本。现有的处理函数就是这样返回的。等某个页面需要区分不同错误时，再改成 JSON。

## 不显示的

负载值。空闲的板子上它读数约为 10：厂商媒体框架的十个线程在等活干时处于不可中断睡眠，每个计为 1.0。`cpuUsagePercent` 和 `npuUsagePercent` 表达的才是它本该表达的意思。
