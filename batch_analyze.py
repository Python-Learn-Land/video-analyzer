#!/usr/bin/env python3
"""
批量视频分析脚本 —— 按顺序处理文件夹中的所有视频。

用法:
    python batch_analyze.py <视频文件夹> [--config <配置目录>]

示例:
    python batch_analyze.py ./videos
    python batch_analyze.py ./videos --config ./my_config
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts', '.m2ts'}

logger = logging.getLogger(__name__)


def load_analyzer_config(config_dir: Path) -> Dict[str, Any]:
    """读取 video-analyzer 的配置文件。"""
    user_config = config_dir / "config.json"
    default_config = config_dir / "default_config.json"

    if user_config.exists():
        with open(user_config, encoding='utf-8') as f:
            return json.load(f)
    elif default_config.exists():
        with open(default_config, encoding='utf-8') as f:
            return json.load(f)
    else:
        return {}


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


def build_command(video_path: Path, config_dir: Path | None) -> List[str]:
    """构建 video-analyzer 命令，只透传 --config。"""
    cmd = ["video-analyzer", str(video_path)]
    if config_dir:
        cmd.extend(["--config", str(config_dir)])
    return cmd


def process_video(video_path: Path, config_dir: Path | None, index: int, total: int) -> bool:
    """处理单个视频，返回是否成功。"""
    logger.info(f"\n{'='*60}")
    logger.info(f"[{index}/{total}] 开始处理: {video_path.name}")
    logger.info(f"{'='*60}")

    cmd = build_command(video_path, config_dir)
    logger.debug(f"执行命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=False,
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
        logger.error("❌ 找不到 video-analyzer 命令。请先安装: pip install -e .")
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
  %(prog)s ./videos
  %(prog)s ./videos --config ./my_config
        """
    )
    parser.add_argument("folder", type=str, help="包含视频的文件夹路径")
    parser.add_argument("--config", type=str, default=None, help="video-analyzer 配置目录（透传）")
    parser.add_argument("--dry-run", action="store_true", help="只列出视频，不执行")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    folder = Path(args.folder).expanduser().resolve()
    config_dir = Path(args.config).expanduser().resolve() if args.config else None

    # 从配置中读取输出目录（仅用于日志汇总）
    output_dir = None
    if config_dir:
        config = load_analyzer_config(config_dir)
        raw_output = config.get("output_dir")
        if raw_output:
            output_dir = Path(str(raw_output)).resolve()

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
        if process_video(video, config_dir, i, len(videos)):
            success_count += 1
        else:
            fail_count += 1
            logger.info("⏳ 继续处理下一个视频...")

    # 汇总
    logger.info(f"\n{'='*60}")
    logger.info("批量处理完成")
    logger.info(f"  成功: {success_count}/{len(videos)}")
    logger.info(f"  失败: {fail_count}/{len(videos)}")
    if output_dir:
        logger.info(f"  输出目录: {output_dir}")
    logger.info(f"{'='*60}")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()