# MotionSense Web 界面

[English](README.md) | 简体中文

最后编辑：2026-10-24

一个现代化、响应式的 Web 界面，用于运行在 Luckfox Pico RV1106 平台上的 MotionSense 监控系统。

## 🚀 功能特性

- **实时视频流**：带状态指示的实时 MJPEG 视频流
- **运动检测热力图**：以可视化方式呈现运动强度的交互式日历
- **视频回放**：带运动点标记的 HLS 视频片段
- **响应式设计**：适用于桌面和移动设备的现代化 UI
- **单页应用**：流畅导航，无需重新加载页面

## 📁 项目结构

```
www/html/
├── index.html              # Main application entry point
├── css/
│   ├── styles.css          # Main application styles
│   ├── calendar.css        # Calendar and heatmap styles
│   └── playback.css        # Video player styles
├── js/
│   ├── app.js             # Main application controller
│   ├── stream.js          # Live stream management
│   ├── calendar.js        # Calendar and heatmap logic
│   └── playback.js        # Video playback and motion markers
└── components/            # Reusable UI components
```

## 🏗️ 架构

该 Web 界面是一个使用原生 JavaScript ES6 类构建的**单页应用（SPA）**：

- **模块化设计**：每个功能都封装在独立的类中
- **事件驱动**：组件之间通过事件进行通信
- **响应式**：使用 CSS Grid 和 Flexbox 实现自适应布局
- **渐进增强**：在没有 JavaScript 的情况下也能提供基本功能

### 核心类

- `MotionSenseApp`：主应用控制器
- `StreamApp`：实时视频流管理
- `CalendarApp`：日历与运动检测热力图
- `PlaybackApp`：带运动标记的视频回放

## 🌐 API 参考

### 基础 URL
```
http://192.168.1.1
```

### 1. 运动计数 API

**端点：** `GET /api/motion_counts`

**说明：** 获取用于热力图日历的每日运动计数。

**响应格式：**
```json
{
  "motion_counts": [
    {
      "date": "2025-07-26",
      "count": 156
    },
    {
      "date": "2025-07-25", 
      "count": 89
    }
  ]
}
```

**使用示例：**
```javascript
const response = await fetch('/api/motion_counts');
const data = await response.json();
console.log(data.motion_counts);
```

### 2. 视频片段 API

**端点：** `GET /api/video_segments?date={date}`

**说明：** 获取指定日期的视频片段。

**参数：**
- `date`（string）：YYYY-MM-DD 格式的日期（可选，默认为今天）

**响应格式：**
```json
{
  "segments": [
    {
      "folder": "00000",
      "start_time": "10:30:15",
      "length": 120,
      "url": "/mnt/sdcard/DCIM/2025-07-26/00000/index.m3u8"
    },
    {
      "folder": "00001", 
      "start_time": "10:32:35",
      "length": 180,
      "url": "/mnt/sdcard/DCIM/2025-07-26/00001/index.m3u8"
    }
  ]
}
```

**使用示例：**
```javascript
const response = await fetch('/api/video_segments?date=2025-07-26');
const data = await response.json();
console.log(data.segments);
```

### 3. 运动点 API

**端点：** `GET /api/motion_points?date={date}`

**说明：** 获取视频片段的运动检测点。

**参数：**
- `date`（string）：YYYY-MM-DD 格式的日期（可选，默认为今天）

**响应格式：**
```json
{
  "motion_points": [
    {
      "video_id": 1,
      "motion_time": 45,
      "folder": "00000"
    },
    {
      "video_id": 1,
      "motion_time": 67,
      "folder": "00000"
    },
    {
      "video_id": 2,
      "motion_time": 12,
      "folder": "00001"
    }
  ]
}
```

**使用示例：**
```javascript
const response = await fetch('/api/motion_points?date=2025-07-26');
const data = await response.json();
console.log(data.motion_points);
```

### 4. 实时视频流 API

**端点：** `GET /api/stream`

**说明：** 提供 MJPEG 实时视频流。

**响应：** MJPEG 视频流

**使用示例：**
```html
<img src="/api/stream" alt="Live Stream" />
```

## 🎨 UI 组件

### 导航
主导航提供三个视图：
- **实时监控**：实时视频画面
- **历史记录**：运动检测热力图与日期选择
- **回放**：带运动标记的视频片段

### 日历热力图
- **颜色深浅**：红色的深浅表示运动频率
- **交互式**：点击日期查看视频片段
- **响应式**：适配不同的屏幕尺寸

### 视频播放器
- **HLS 支持**：使用 Video.js 进行 HLS 播放
- **运动标记**：进度条上的红线表示运动事件
- **点击导航**：点击标记即可跳转到运动事件
- **片段列表**：可用视频片段的列表

## 🔧 开发

### 前置条件
- 支持 ES6 的现代 Web 浏览器
- 能够通过网络访问 MotionSense 设备

### 本地开发
1. 克隆仓库
2. 使用 Web 服务器托管 `www/html` 目录
3. 通过 `http://localhost:port` 访问

### 浏览器兼容性
- Chrome 60+
- Firefox 55+
- Safari 12+
- Edge 79+

## 📱 响应式设计

该界面使用 CSS Grid 和 Flexbox 实现响应式布局：

```css
/* Mobile-first approach */
.container {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}

/* Tablet and desktop */
@media (min-width: 768px) {
  .container {
    grid-template-columns: 1fr 1fr;
  }
}
```

## 🎯 运动标记系统

### 工作原理
1. **数据获取**：从 `/api/motion_points` 获取运动点
2. **时间计算**：将帧号转换为视频时间（30fps）
3. **位置映射**：将时间映射到进度条上的位置
4. **可视化渲染**：在进度条上创建可点击的标记

### 标记属性
- **宽度**：2px（悬停时为 4px）
- **颜色**：红色（#ff4444）
- **位置**：根据 motion_time 和视频时长计算
- **交互**：点击即可跳转到运动事件

## 🔍 调试

### 控制台日志
应用包含全面的日志记录：

```javascript
// Enable debug logging
console.log('Motion points loaded:', motionPoints);
console.log('Video segments:', segments);
console.log('Stream status:', streamStatus);
```

### 网络监控
在浏览器 DevTools 中监控 API 调用：
- 运动计数：`/api/motion_counts`
- 视频片段：`/api/video_segments`
- 运动点：`/api/motion_points`
- 实时视频流：`/api/stream`

## 🚀 性能优化

### 加载策略
- **懒加载**：组件按需加载
- **缓存**：在合适的地方缓存 API 响应
- **防抖**：对输入事件进行防抖处理以提升性能

### 内存管理
- **事件清理**：正确移除事件监听器
- **DOM 清理**：重新创建标记前先清除旧标记
- **资源管理**：释放视频播放器资源

## 🔒 安全注意事项

- **CORS**：配置为允许局域网访问
- **输入验证**：对 API 参数进行验证
- **错误处理**：API 失败时平稳降级

## 📊 数据流

```
User Interaction → Event Handler → API Call → Data Processing → UI Update
     ↓
Calendar Click → Load Segments → Fetch Motion Points → Create Markers
     ↓
Video Play → Update Progress → Show Motion Indicators
```

## 🛠️ 故障排除

### 常见问题

**运动标记不显示：**
- 检查 API 响应格式
- 确认可以获取视频时长
- 确保运动点与当前片段匹配

**视频无法播放：**
- 确认 HLS 流可以访问
- 检查网络连接
- 确保 Video.js 已加载

**日历无法加载：**
- 检查运动计数 API
- 确认日期格式
- 检查浏览器控制台中的错误

### 错误处理
```javascript
try {
  const response = await fetch('/api/motion_points');
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const data = await response.json();
} catch (error) {
  console.error('API Error:', error);
  // Handle gracefully
}
```

## 📈 未来增强

- **实时更新**：通过 WebSocket 推送实时运动告警
- **高级筛选**：按运动强度筛选
- **导出功能**：导出视频片段
- **移动应用**：原生移动应用
- **云端集成**：远程监控能力

---

**版本：** 2.0.0  
**兼容性：** MotionSense v1.3.0+
