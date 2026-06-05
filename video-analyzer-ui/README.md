# Video Analyzer UI

video-analyzer 工具的轻量级 Web 界面。

## 功能特性
- 简洁直观的视频分析界面
- 实时命令输出流
- 拖拽上传视频
- 结果可视化与下载
- 会话管理与清理

## 环境要求
- Python 3.8 或更高版本
- 已安装 video-analyzer 包
- FFmpeg（video-analyzer 所需）

## 安装

```bash
pip install video-analyzer-ui
```

## 快速开始

1. 启动服务：
   ```bash
   video-analyzer-ui
   ```

2. 在浏览器中打开：
   http://localhost:5000

## 使用方法

### 开发模式
```bash
video-analyzer-ui --dev
```
- 代码变更自动重载
- 调试日志
- 开发错误页面

### 生产模式
```bash
video-analyzer-ui --host 0.0.0.0 --port 5000
```
- 性能优化
- 错误日志写入文件
- 生产级安全

### 命令行选项
- `--dev`: 启用开发模式
- `--host`: 绑定地址（默认：localhost）
- `--port`: 端口号（默认：5000）
- `--log-file`: 日志文件路径
- `--config`: 自定义配置文件路径

## 开发环境搭建

1. 克隆仓库：
   ```bash
   git clone https://github.com/username/video-analyzer-ui.git
   cd video-analyzer-ui
   ```

2. 创建虚拟环境：
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows 系统：venv\Scripts\activate
   ```

3. 安装依赖：
   ```bash
   pip install -e .
   ```

4. 运行开发服务器：
   ```bash
   video-analyzer-ui --dev
   ```

## 工作原理

1. **上传视频：**
   - 拖拽或选择视频文件
   - 文件临时存储在会话专属目录中

2. **配置分析：**
   - 必填项标有 *
   - 可选参数可留空
   - 实时命令预览显示将要执行的命令

3. **运行分析：**
   - 实时显示进度
   - 输出实时流式传输
   - 结果存储在会话目录中

4. **查看结果：**
   - 下载 analysis.json
   - 查看提取的帧（如果保留）
   - 访问转录文本和其他输出

## 开源协议

Apache License
