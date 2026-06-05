# 视频分析器设计文档
![设计](design.png)
## 核心工作流

1. **帧提取**
   - 使用 OpenCV 从视频中提取帧
   - 计算帧差异以识别关键时刻
   - 将帧保存为 JPEG 格式供 LLM 分析
   - 基于视频长度和目标每分钟帧数进行自适应采样

   ### 帧选择算法
   1. **目标帧数计算**
      - 根据视频时长和 frames_per_minute 计算目标帧数
      - 遵守可选的 max_frames 限制
      - 确保至少提取 1 帧，且不超过视频总帧数

   2. **自适应采样**
      - 使用采样间隔 = total_frames / (target_frames * 2)
      - 在降低处理负载的同时保持覆盖度
      - 比目标采样更频繁，以确保有足够的候选帧

   3. **帧差异分析**
      - 将帧转换为灰度图以进行高效比较
      - 使用 OpenCV 的 absdiff 计算绝对差异
      - 与 FRAME_DIFFERENCE_THRESHOLD（默认 10.0）进行比较
      - 存储帧编号、图像数据和差异分数

   4. **最终选择过程**
      - 选择差异分数最高的帧
      - 根据目标帧数取前 N 帧
      - 如果指定了 max_frames，则在选中的帧中均匀采样
      - 确保捕捉到最显著的变化

   ### 局限性
   - 采样间隔之间的帧可能会被遗漏
   - 快速序列可能只选中一帧
   - 高分帧可能因被其他帧超越而被排除
   - 使用 max_frames 进行均匀采样时可能会跳过一些显著变化

2. **音频处理**
   - 使用 FFmpeg 提取音频
   - 使用 Whisper 进行转录
   - 通过检查置信度分数处理低质量音频
   - 对音频进行分段以获得更好的最终分析上下文

3. **帧分析**
   - 使用视觉 LLM 独立分析每一帧
   - 使用 frame_analysis.txt 提示词引导 LLM 分析
   - 捕捉时间戳、视觉元素和动作
   - 保持时间顺序以确保叙述流畅

4. **视频重建**
   - 按时间顺序合并帧分析结果
   - 如有音频转录则进行整合
   - 使用 video_reconstruction.txt 提示词创建技术性描述
   - 使用 narrate_storyteller.txt 转换为引人入胜的叙述

## LLM 集成

### 基础客户端 (llm_client.py)
```python
class LLMClient:
    def encode_image(self, image_path: str) -> str:
        # 所有客户端通用的 base64 编码
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    @abstractmethod
    def generate(self,
        prompt: str,
        image_path: Optional[str] = None,
        stream: bool = False,
        model: str = "llama3.2-vision",
        temperature: float = 0.2,
        num_predict: int = 256) -> Dict[Any, Any]:
        pass
```

### 客户端实现

1. **Ollama (ollama.py)**
   - 使用本地 Ollama API
   - 在 "images" 数组中发送 base64 编码的图片
   - 返回 Ollama 的原始响应

2. **通用 OpenAI API (generic_openai_api.py)**
   - 兼容 OpenAI 风格的 API（OpenAI、OpenRouter 等）
   - 可配置的 API URL（例如 OpenRouter: https://openrouter.ai/api/v1, OpenAI: https://api.openai.com/v1）
   - 以 type 为 "image_url" 的内容数组形式发送图片
   - 需要 API 密钥和服务 URL
   - 返回标准化的响应格式

## 配置系统

采用级联优先级：
1. 命令行参数
2. 用户配置 (config.json)
3. 默认配置 (default_config.json)

关键配置组：
```json
{
    "clients": {
        "default": "ollama",
        "ollama": {
            "url": "http://localhost:11434",
            "model": "llama3.2-vision"
        },
        "openai_api": {
            "api_key": "",
            "api_url": "https://openrouter.ai/api/v1",
            "model": "meta-llama/llama-3.2-11b-vision-instruct:free"
        }
    },
    "frames": {
        "per_minute": 60,
        "analysis_threshold": 10.0,
        "min_difference": 5.0,
        "max_count": 30
    }
}
```

## 提示词系统

### 提示词文件

两个关键提示词：

1. **frame_analysis.txt**
   - 分析单帧
   - 包含时间戳上下文
   - 关注视觉元素和动作
   - 通过 {prompt} 令牌支持用户问题

2. **describe.txt**
   - 合并帧分析结果
   - 使用 1 帧
   - 整合转录文本
   - 基于所有过往帧创建视频描述
   - 通过 {prompt} 令牌支持用户问题

两个提示词都通过 --prompt 标志支持用户问题。当提供问题时，会以 "I want to know" 为前缀，并使用 {prompt} 令牌注入到提示词中。这允许用户提出关于视频的具体问题，引导帧分析和最终描述。

### 提示词加载系统

提示词加载系统支持灵活的提示词文件位置和自定义提示词：

1. **路径解析：**
   - 用户指定的目录（通过配置 `prompt_dir`）：
     * 绝对路径：`/path/to/prompts`
     * 用户主目录路径：`~/prompts`
     * 相对路径：检查以下位置：
       1. 当前工作目录
       2. 包根目录
   - 包资源（后备）

2. **开发工作流：**
   - 以开发模式安装：`pip install -e .`
   - 直接修改提示词文件
   - 更改立即生效，无需重新安装
   - 可在任何目录下工作

3. **配置：**
```json
{
    "prompt_dir": "/absolute/path/to/prompts",  // 绝对路径
    // 或 "~/prompts"                          // 用户主目录
    // 或 "prompts"                            // 相对路径
    // 或 ""                                   // 仅使用包内提示词
    "prompts": [
        {
            "name": "Frame Analysis",
            "path": "frame_analysis/frame_analysis.txt"
        },
        {
            "name": "Video Reconstruction",
            "path": "frame_analysis/describe.txt"
        }
    ]
}
```

系统优先使用用户指定的提示词而非包内提示词，在保持可靠后备机制的同时支持自定义。

## 示例输出
[示例输出](sample_analysis.json)

## 常见问题与解决方案

1. **帧分析失败**
   - Ollama：检查服务是否运行且模型已加载
   - OpenRouter：验证 API 密钥并检查响应格式
   - 两者：确保图像编码对每个 API 都正确

2. **内存使用**
   - 根据视频长度调整 frames_per_minute
   - 分析后清理帧文件
   - 使用适当大小的 Whisper 模型

3. **分析质量不佳**
   - 检查帧提取阈值
   - 验证提示词模板
   - 确保使用了正确的模型

## 添加新功能

1. **新增 LLM 提供商**
   - 继承自 LLMClient
   - 为 API 实现正确的图像格式
   - 在 default_config.json 中添加客户端配置
   - 在 video_analyzer.py 中更新 create_client()

2. **自定义分析**
   - 添加新的提示词模板
   - 更新 VideoAnalyzer 方法
   - 修改结果中的输出格式
