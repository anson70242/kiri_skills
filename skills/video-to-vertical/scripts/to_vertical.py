import argparse
import subprocess
import sys
from pathlib import Path

def convert_to_vertical(input_file: str, mode: str):
    input_path = Path(input_file)
    
    if not input_path.is_file():
        print(f"[ERROR] File not found: '{input_file}'")
        sys.exit(1)

    output_path = input_path.with_name(f"vertical_{input_path.name}")

    command = [
        "ffmpeg",
        "-y",
        "-hwaccel", "auto",
        "-i", str(input_path),
    ]

    if mode == "black":
        # Pure black padding mode
        vf_filter = (
            "format=yuv420p,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            "format=yuv420p"
        )
        command.extend(["-vf", vf_filter])
    else:
        # Blurred background mode
        filter_complex = (
            "[0:v]format=yuv420p,split=2[bg_in][fg_in];"
            "[bg_in]scale=272:480:force_original_aspect_ratio=increase,"
            "crop=272:480,gblur=sigma=15,eq=brightness=-0.15,scale=1080:1920[bg];"
            "[fg_in]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
        )
        command.extend(["-filter_complex", filter_complex])

    command.extend([
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-rc", "vbr",
        "-cq", "20",
        "-c:a", "copy",
        str(output_path)
    ])

    print(f"[INFO] Input file:  {input_path}")
    print(f"[INFO] Output file: {output_path}")
    print(f"[INFO] Mode:        {mode}")
    print("-" * 40)

    try:
        subprocess.run(command, check=True)
        print("-" * 40)
        print(f"[SUCCESS] Conversion completed: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Conversion failed with FFmpeg exit code: {e.returncode}")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\n[WARNING] Process interrupted by user.")
        sys.exit(130)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert horizontal video to 1080x1920 vertical format."
    )
    parser.add_argument(
        "input",
        nargs="+",
        help="Path to input video file(s)."
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["blur", "black"],
        default="blur",
        help="Background fill mode: 'blur' (default) or 'black'."
    )
    args = parser.parse_args()

    for file_path in args.input:
        convert_to_vertical(file_path, args.mode)