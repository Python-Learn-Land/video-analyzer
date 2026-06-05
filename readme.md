# 使用 Llama3.2 Vision 和 OpenAI Whisper 等视觉模型的视频分析

一个视频分析工具，结合 Llama 11B 视觉模型和 Whisper，通过提取关键帧并送入视觉模型获取细节信息，从而生成视频描述。该工具利用每一帧的细节信息和转录文本（如有）来描述视频中的内容。

## 目录
- [功能特性](#功能特性)
- [环境要求](#环境要求)
  - [系统要求](#系统要求)
  - [安装步骤](#安装步骤)
  - [Ollama 配置](#ollama-配置)
  - [OpenAI 兼容 API 配置（可选）](#openai-兼容-api-配置可选)
- [使用方法](#使用方法)
  - [快速开始](#快速开始)
  - [输出示例](#输出示例)
  - [完整使用指南](docs/USAGES.md)
- [设计说明](#设计说明)
  - [详细设计文档](docs/DESIGN.md)
- [项目结构](#项目结构)
- [配置说明](#配置说明)
- [输出结果](#输出结果)
- [提示词调优](#提示词调优)
- [卸载方法](#卸载方法)
- [开源协议](#开源协议)
- [贡献指南](#贡献指南)

## 功能特性
- 💻 可完全在本地运行，无需云服务或 API 密钥
- ☁️  或利用任何兼容 OpenAI API 的大语言模型服务（如 OpenRouter、OpenAI 等）以获得更快的速度和更大的规模
- 🎬 智能视频关键帧提取
- 🔊 使用 OpenAI Whisper 进行高质量音频转录
- 👁️ 通过 Ollama 和 Llama3.2 11B 视觉模型进行帧分析
- 📝 自然语言描述视频内容
- 🔄 自动处理低质量音频
- 📊 详细的 JSON 格式分析结果
- ⚙️ 支持通过命令行参数或配置文件进行高度自定义配置

## 设计说明
系统分为三个阶段运行：

1. **帧提取与音频处理**
   - 使用 OpenCV 提取关键帧
   - 使用 Whisper 进行音频转录处理
   - 通过置信度检查处理低质量音频

2. **帧分析**
   - 使用视觉大语言模型分析每一帧
   - 每次分析都包含之前帧的上下文信息
   - 保持时间顺序推进
   - 使用 frame_analysis.txt 提示词模板

3. **视频重建**
   - 按时间顺序合并帧分析结果
   - 整合音频转录文本
   - 使用第一帧设定场景
   - 生成全面的视频描述

![设计](docs/design.png)

## 环境要求

### 系统要求
- Python 3.11 或更高版本
- FFmpeg（音频处理必需）
- 本地运行大语言模型时（使用 OpenRouter 时不需要）
  - 至少 16GB 内存（推荐 32GB）
  - GPU 显存至少 12GB，或 Apple M 系列芯片且内存至少 32GB

### 安装步骤

1. 克隆代码仓库：
```bash
git clone https://github.com/byjlw/video-analyzer.git
cd video-analyzer
```

2. 创建并激活虚拟环境：
```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows 系统：.venv\Scripts\activate
```

3. 安装软件包：
```bash
pip install .  # 常规安装
# 或
pip install -e .  # 开发模式安装
```

4. 安装 FFmpeg：
- Ubuntu/Debian：
  ```bash
  sudo apt-get update && sudo apt-get install -y ffmpeg
  ```
- macOS：
  ```bash
  brew install ffmpeg
  ```
- Windows：
  ```bash
  choco install ffmpeg
  ```

### Ollama 配置

1. 按照 [ollama.ai](https://ollama.ai) 的说明安装 Ollama

2. 拉取默认视觉模型：
```bash
ollama pull llama3.2-vision
```

3. 启动 Ollama 服务：
```bash
ollama serve
```

### OpenAI 兼容 API 配置（可选）

如果你想使用兼容 OpenAI 的 API（如 OpenRouter 或 OpenAI）替代 Ollama：

1. 从服务商获取 API 密钥：
   - [OpenRouter](https://openrouter.ai)
   - [OpenAI](https://platform.openai.com)

2. 通过命令行配置：
   ```bash
   # OpenRouter
   video-analyzer video.mp4 --client openai_api --api-key your-key --api-url https://openrouter.ai/api/v1 --model gpt-4o

   # OpenAI
   video-analyzer video.mp4 --client openai_api --api-key your-key --api-url https://api.openai.com/v1 --model gpt-4o
   ```

   或添加到 config/config.json：
   ```json
   {
     "clients": {
       "default": "openai_api",
       "openai_api": {
         "api_key": "your-api-key",
         "api_url": "https://openrouter.ai/api/v1"  // 或 https://api.openai.com/v1
       }
     }
   }
   ```

注意：使用 OpenRouter 时，你可以在模型名称后添加 :free 来免费使用 llama 3.2 11b vision 模型

## 设计说明

有关项目设计和实现的详细信息，包括如何进行修改，请参阅 [docs/DESIGN.md](docs/DESIGN.md)。

## 使用方法

有关详细的使用说明和所有可用选项，请参阅 [docs/USAGES.md](docs/USAGES.md)。

### 快速开始

```bash
# 使用 Ollama 进行本地分析（默认）
video-analyzer video.mp4

# 使用 OpenRouter 进行云端分析
video-analyzer video.mp4 \
    --client openai_api \
    --api-key your-key \
    --api-url https://openrouter.ai/api/v1 \
    --model meta-llama/llama-3.2-11b-vision-instruct:free

# 使用自定义提示词进行分析
video-analyzer video.mp4 \
    --prompt "视频中发生了什么活动？" \
    --whisper-model large
```

## 输出结果

该工具会生成一个 JSON 文件（`output/analysis.json`），包含以下内容：
- 分析元数据
- 音频转录文本（如有）
- 逐帧分析结果
- 最终视频描述

### 输出示例
```
视频开始时，一位留着金色长发、身穿粉色T恤和黄色短裤的人站在一个带轮子的黑色塑料桶或容器前。地面似乎铺满了木屑。

随着视频推进，这个人一直背对着镜头，低头看着桶里的东西。...
```
完整的示例输出见 `docs/sample_analysis.json`

## 配置说明

该工具采用级联配置系统，命令行参数优先级最高，其次是用户配置（config/config.json），最后是默认配置。有关详细的配置选项，请参阅 [docs/USAGES.md](docs/USAGES.md)。


## 提示词调优

用于驱动帧分析和视频重建的提示词可以通过 [video-analyzer-tune](video-analyzer-tune/README.md) 针对你的特定内容和用例进行自动优化。

```bash
pip install video-analyzer-tune
```

在几个有代表性的视频上运行 `video-analyzer`，编辑输出结果以展示理想的效果，然后让 DSPy MIPROv2 自动找到更好的提示词指令。调优后的提示词会写入新文件，你可以通过配置指向这些文件——主包不受影响。

完整说明请参阅 [video-analyzer-tune/README.md](video-analyzer-tune/README.md)。

## 卸载方法

卸载软件包：
```bash
pip uninstall video-analyzer
```

## 开源协议

Apache License

## 贡献指南

我们欢迎贡献！请参阅 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) 了解如何：
- 了解项目设计
- 通过 GitHub Discussions 提出修改建议
- 提交拉取请求
