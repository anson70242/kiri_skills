# down_video.py
import argparse
import sys
import traceback

from core import get_base_path, configure_utf8_stdio, DownloadPipeline


def main() -> int:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="down_video.py",
        description="AutoKiri-Flow [video only] Download the VOD without fetching chat.",
    )
    parser.add_argument("--link", required=True, help="URL of the video to process")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Continue even when the streamer cannot be identified "
             "(usually means the cookie / OAuth token has expired)",
    )
    args = parser.parse_args()

    print("=" * 60 + "\n       AutoKiri-Flow [video only]       \n" + "=" * 60)

    pipeline = DownloadPipeline(get_base_path())
    result = pipeline.process(
        args.link,
        download_video=True,
        download_chat=False,
        assume_yes=args.yes,
    )
    return 0 if result else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\n" + "!" * 60, file=sys.stderr)
        print("[Fatal] The program crashed while running:", file=sys.stderr)
        traceback.print_exc()
        print("!" * 60, file=sys.stderr)
        sys.exit(1)
