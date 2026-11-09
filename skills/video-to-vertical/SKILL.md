---
name: video-to-vertical
description: Convert horizontal (16:9 / 1920x1080) videos into vertical (9:16 / 1080x1920) format using FFmpeg with NVIDIA GPU acceleration (h264_nvenc). Supports blurred glass background or pure black padding. Trigger this skill whenever the user asks to convert video to vertical/portrait, make a video suitable for YouTube Shorts/TikTok/Reels, resize 16:9 to 9:16, or add blurred/black top-and-bottom padding to a video.
---

# Video to Vertical Converter

This skill converts horizontal videos into `1080x1920` vertical videos by scaling the original video proportionally to fit the width (`1080px`), centering it vertically, and filling the top/bottom space with either a darkened Gaussian-blurred background (`blur`) or solid black bars (`black`).

## Prerequisites
- System `ffmpeg` installed with `h264_nvenc` support (NVIDIA GPU).
- Python 3.x installed.

## Script Location
Assume the execution script is located at:
`scripts/to_vertical.py` (relative to this skill directory, or adjust to your absolute path).

## Usage & Command Mapping

Execute the Python script via shell/bash tool:

```bash
python <path_to_skill>/scripts/to_vertical.py <input_file_1> [input_file_2 ...] -m <mode>
```

### Parameters
| Parameter      | Required | Values          | Default | Description                                                  |
| :------------- | :------- | :-------------- | :------ | :----------------------------------------------------------- |
| `input`        | Yes      | File path(s)    | N/A     | One or more input video file paths (supports wildcards like `*.mp4`). |
| `-m`, `--mode` | No       | `blur`, `black` | `blur`  | Background fill style. Use `blur` for frosted glass background, `black` for solid black bars. |

### Output Behavior
- The script automatically outputs the converted file in the **same directory** as the input file.
- Output filename format: `vertical_<original_filename>` (e.g., `/path/to/clip.mp4` -> `/path/to/vertical_clip.mp4`).
- Audio stream is copied directly (`-c:a copy`) without re-encoding.

## Agent Execution Rules

1. **Intent Parsing**:
   - If the user does not specify a background style, or asks for "毛玻璃", "模糊背景", "blurred background", use `-m blur`.
   - If the user asks for "黑边", "上下留黑", "纯黑背景", "black bars/padding", use `-m black`.
2. **Path Resolution**:
   - Always resolve the user's target video path before executing. If the user says "把当前目录下的视频转成竖屏", check the working directory for `.mp4`/`.mkv`/`.mov` files first.
3. **Fallback Direct Execution (If Script of python is Missing)**:
   - If `to_vertical.py` is not found in the environment, run the `ffmpeg` command directly via bash:
   - **Blur Mode**:
     ```bash
     ffmpeg -y -hwaccel auto -i "<INPUT>" -filter_complex "[0:v]format=yuv420p,split=2[bg_in][fg_in];[bg_in]scale=272:480:force_original_aspect_ratio=increase,crop=272:480,gblur=sigma=15,eq=brightness=-0.15,scale=1080:1920[bg];[fg_in]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p" -c:v h264_nvenc -preset p4 -rc vbr -cq 20 -c:a copy "<OUTPUT_DIR>/vertical_<FILENAME>"
     ```
   - **Black Mode**:
     ```bash
     ffmpeg -y -hwaccel auto -i "<INPUT>" -vf "format=yuv420p,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p" -c:v h264_nvenc -preset p4 -rc vbr -cq 20 -c:a copy "<OUTPUT_DIR>/vertical_<FILENAME>"
     ```

## Examples of Natural Language Triggers

- **User**: "帮我把 `test.mp4` 转成竖屏"
  - **Action**: `python scripts/to_vertical.py test.mp4 -m blur`
- **User**: "把 `clip1.mp4` 和 `clip2.mp4` 改成 9:16 竖屏，上下留黑边"
  - **Action**: `python scripts/to_vertical.py clip1.mp4 clip2.mp4 -m black`
- **User**: "把这个文件夹下所有的 mp4 都做成带模糊背景的 Shorts 格式"
  - **Action**: `python scripts/to_vertical.py *.mp4 -m blur`