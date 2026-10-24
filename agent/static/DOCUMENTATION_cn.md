# MotionSense Web 界面文档

[English](DOCUMENTATION.md) | 简体中文

最后编辑：2026-10-24

MotionSense Web 界面的完整文档。

## 📚 文档索引

### 🚀 入门
- **[快速入门指南](QUICKSTART_cn.md)** - 几分钟内即可上手
- **[主文档](README_cn.md)** - 完整的 API 参考与架构说明
- **[API 测试指南](API_TESTING_cn.md)** - 全面的测试示例

## 📖 文档概览

### 快速入门指南（`QUICKSTART.md`）
**适用对象：** 最终用户、首次设置
**内容：**
- 分步设置说明
- 界面概览
- 常见问题排查
- 移动端使用技巧
- 性能优化

### 主文档（`README.md`）
**适用对象：** 开发人员、系统管理员
**内容：**
- 完整的 API 参考
- 架构概览
- 开发指南
- 浏览器兼容性
- 安全注意事项

### API 测试指南（`API_TESTING.md`）
**适用对象：** 开发人员、QA 测试人员
**内容：**
- 测试工具与示例
- 响应验证
- 错误处理
- 性能测试
- 调试技巧

## 🎯 快速导航

### 最终用户
1. 从 **[快速入门指南](QUICKSTART_cn.md)** 开始
2. 使用 **[主文档](README_cn.md)** 作为参考
3. 遇到问题时查看故障排除部分

### 开发人员
1. 阅读 **[主文档](README_cn.md)** 了解架构
2. 使用 **[API 测试指南](API_TESTING_cn.md)** 辅助开发
3. 参考主文档中的 API 示例

### 系统管理员
1. 查阅 **[主文档](README_cn.md)** 了解部署
2. 查看安全注意事项
3. 使用 **[API 测试指南](API_TESTING_cn.md)** 进行监控

## 🔗 API 端点汇总

| 端点 | 方法 | 说明 | 文档 |
|----------|--------|-------------|---------------|
| `/api/motion_counts` | GET | 每日运动计数 | [README_cn.md](README_cn.md#1-运动计数-api) |
| `/api/video_segments` | GET | 按日期获取视频片段 | [README_cn.md](README_cn.md#2-视频片段-api) |
| `/api/motion_points` | GET | 运动检测点 | [README_cn.md](README_cn.md#3-运动点-api) |
| `/api/stream` | GET | 实时 MJPEG 视频流 | [README_cn.md](README_cn.md#4-实时视频流-api) |

## 🛠️ 开发资源

### 代码结构
```
www/html/
├── index.html              # Main application
├── css/                    # Stylesheets
├── js/                     # JavaScript modules
├── components/             # UI components
└── *.md                   # Documentation
```

### 关键文件
- `app.js` - 主应用控制器
- `stream.js` - 实时视频流管理
- `calendar.js` - 日历与热力图
- `playback.js` - 带运动标记的视频回放

### 测试工具
- 浏览器 DevTools 控制台
- cURL 命令
- JavaScript 测试套件
- 负载测试脚本

## 📊 系统要求

### 硬件
- **设备**：Luckfox Pico RV1106
- **内存**：256MB（Web 服务器可用 150MB）
- **存储**：256MB Nand Flash（可用 150MB）

### 软件
- **Web 服务器**：Mongoose（基于 C 的轻量级服务器）
- **数据库**：SQLite
- **视频**：HLS（HTTP Live Streaming）
- **视频流**：MJPEG

### 浏览器支持
- Chrome 60+
- Firefox 55+
- Safari 12+
- Edge 79+

## 🔍 故障排除索引

### 常见问题
| 问题 | 解决方法 | 文档 |
|-------|----------|---------------|
| 无法访问界面 | 检查 IP 和网络连接 | [快速入门](QUICKSTART_cn.md#-故障排除) |
| 实时视频流无法工作 | 检查摄像头和设备状态 | [快速入门](QUICKSTART_cn.md#-故障排除) |
| 没有运动标记 | 验证 API 和数据 | [API 测试](API_TESTING_cn.md#-响应验证) |
| 日历无法加载 | 检查运动计数 API | [API 测试](API_TESTING_cn.md#运动计数验证) |

### 调试工具
- 浏览器控制台日志
- 网络监控
- API 响应验证
- 性能测试

## 📈 性能指南

### 优化技巧
- 观看视频时使用有线连接
- 关闭不必要的浏览器标签页
- 定期清除浏览器缓存
- 监控 API 响应时间

### 监控
- 检查 API 响应时间
- 监控内存使用情况
- 跟踪视频播放性能
- 验证数据完整性

## 🔒 安全说明

### 网络安全
- 仅限局域网访问
- 无需互联网连接
- 已为本地访问配置 CORS
- 所有 API 均进行输入验证

### 最佳实践
- 保持设备固件为最新版本
- 监控访问日志
- 验证 API 响应
- 平稳地处理错误

## 📞 支持资源

### 自助
1. 查阅文档
2. 使用故障排除指南
3. 测试 API 端点
4. 查看错误日志

### 开发支持
- API 测试工具
- 调试日志
- 性能监控
- 错误处理示例

---

**文档版本：** 2.0.0  
**维护者：** MotionSense 开发团队
