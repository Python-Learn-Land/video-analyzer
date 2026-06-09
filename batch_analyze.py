#!/usr/bin/env python3
"""
批量视频分析脚本 —— 按顺序处理文件夹中的所有视频。

用法示例:
    # 基础用法（使用默认 Ollama）
    python batch_analyze.py /path/to/videos

    # 使用 OpenRouter API
    python batch_analyze.py /path/to/videos --client openai_api --api-key $API_KEY --api-url https://openrouter.ai/api/v1 --model qwen/qwen2.5-vl-72b-instruct

    # 限制每视频最大帧数、保留帧、自定义提示词
    python batch_analyze.py /path/to/videos --max-frames 20 --keep-frames --prompt "总结视频中的教学要点"

    # 只处理前 60 秒、指定输出目录
    python batch_analyze.py /path/to/videos --duration 60 --output ./results
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# 支持的视频文件扩展名
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts'}

logger = logging.getLogger(__name__)


def find_videos(folder: Path) -> List[Path]:
    """查找文件夹中所有视频文件，按文件名排序。"""
    if not folder.exists():
        raise FileNotFoundError(f"文件夹不存在: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"不是文件夹: {folder}")

    videos = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    videos.sort(key=lambda p: p.name.lower())
    return videos


def build_command(video_path: Path, args: argparse.Namespace) -> List[str]:
    """根据参数构建 video-analyzer 命令。"""
    cmd = ["video-analyzer", str(video_path)]

    if args.config:
        cmd.extend(["--config", args.config])
    if args.output:
        cmd.extend(["--output", args.output])
    if args.client:
        cmd.extend(["--client", args.client])
    if args.ollama_url:
        cmd.extend(["--ollama-url", args.ollama_url])
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    if args.api_url:
        cmd.extend(["--api-url", args.api_url])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.duration is not None:
        cmd.extend(["--duration", str(args.duration)])
    if args.keep_frames:
        cmd.append("--keep-frames")
    if args.whisper_model:
        cmd.extend(["--whisper-model", args.whisper_model])
    if args.max_frames is not None:
        cmd.extend(["--max-frames", str(args.max_frames)])
    if args.prompt:
        cmd.extend(["--prompt", args.prompt])
    if args.language:
        cmd.extend(["--language", args.language])
    if args.device:
        cmd.extend(["--device", args.device])
    if args.temperature is not None:
        cmd.extend(["--temperature", str(args.temperature)])
    if args.log_level != "INFO":
        cmd.extend(["--log-level", args.log_level])

    return cmd


def process_video(video_path: Path, args: argparse.Namespace, index: int, total: int) -> bool:
    """处理单个视频，返回是否成功。"""
    logger.info(f"\n{'='*60}")
    logger.info(f"[{index}/{total}] 开始处理: {video_path.name}")
    logger.info(f"{'='*60}")

    cmd = build_command(video_path, args)
    logger.debug(f"执行命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=False,  # 直接输出到终端，方便查看进度
            text=True,
            check=False,
        )
        if result.returncode == 0:
            logger.info(f"✅ [{index}/{total}] 完成: {video_path.name}")
            return True
        else:
            logger.error(f"❌ [{index}/{total}] 失败 (退出码 {result.returncode}): {video_path.name}")
            return False
    except FileNotFoundError:
        logger.error(f"❌ 找不到 video-analyzer 命令。请先安装: pip install -e .")
        return False
    except Exception as e:
        logger.error(f"❌ [{index}/{total}] 异常: {video_path.name} — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="批量分析文件夹中的视频",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s ./videos --max-frames 15 --prompt "描述画面内容"
  %(prog)s ./videos --client openai_api --api-key KEY --model gpt-4o
  %(prog)s ./videos --duration 30 --output ./results --keep-frames
        """
    )
    parser.add_argument("folder", type=str, help="包含视频的文件夹路径")
    parser.add_argument("--config", type=str, default=None, help="配置目录路径")
    parser.add_argument("--output", type=str, default=None, help="输出目录")
    parser.add_argument("--client", type=str, default=None, help="客户端类型 (ollama 或 openai_api)")
    parser.add_argument("--ollama-url", type=str, default=None, help="Ollama 服务 URL")
    parser.add_argument("--api-key", type=str, default=None, help="API Key")
    parser.add_argument("--api-url", type=str, default=None, help="API URL")
    parser.add_argument("--model", type=str, default=None, help="视觉模型名称")
    parser.add_argument("--duration", type=float, default=None, help="只处理前 N 秒")
    parser.add_argument("--keep-frames", action="store_true", help="保留提取的帧")
    parser.add_argument("--whisper-model", type=str, default=None, help="Whisper 模型")
    parser.add_argument("--max-frames", type=int, default=None, help="每视频最大帧数")
    parser.add_argument("--prompt", type=str, default=None, help="分析提示词")
    parser.add_argument("--language", type=str, default=None, help="音频语言")
    parser.add_argument("--device", type=str, default=None, help="计算设备 (cpu/cuda)")
    parser.add_argument("--temperature", type=float, default=None, help="LLM 温度参数")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    parser.add_argument("--dry-run", action="store_true", help="只列出会处理的视频，不实际执行")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    folder = Path(args.folder).expanduser().resolve()

    try:
        videos = find_videos(folder)
    except (FileNotFoundError, NotADirectoryError) as e:
        logger.error(str(e))
        sys.exit(1)

    if not videos:
        logger.warning(f"在 {folder} 中没有找到视频文件")
        logger.info(f"支持的格式: {', '.join(sorted(VIDEO_EXTENSIONS))}")
        sys.exit(0)

    logger.info(f"发现 {len(videos)} 个视频文件（按文件名排序）:")
    for i, v in enumerate(videos, 1):
        logger.info(f"  {i}. {v.name}")

    if args.dry_run:
        logger.info("\n🛑  dry-run 模式，跳过实际处理")
        sys.exit(0)

    # 批量处理
    success_count = 0
    fail_count = 0

    for i, video in enumerate(videos, 1):
        if process_video(video, args, i, len(videos)):
            success_count += 1
        else:
            fail_count += 1
            logger.info(f"⏳ 继续处理下一个视频...")

    # 汇总
    logger.info(f"\n{'='*60}")
    logger.info("批量处理完成")
    logger.info(f"  成功: {success_count}/{len(videos)}")
    logger.info(f"  失败: {fail_count}/{len(videos)}")
    if args.output:
        logger.info(f"  输出目录: {Path(args.output).resolve()}")
    logger.info(f"{'='*60}")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()