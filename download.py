#!/usr/bin/env python3
"""
download.py — download videos, audio, or images from YouTube, Instagram, TikTok, Facebook, Vimeo and more.

Requires: pip install yt-dlp
System:   ffmpeg (for audio conversion and video merging)
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import yt_dlp
    from yt_dlp.utils import DownloadError
except ImportError:
    print("Error: yt-dlp is not installed.\nRun: pip install yt-dlp")
    sys.exit(1)


SITE_MAP = {
    "youtube.com":       "YouTube",
    "youtu.be":          "YouTube",
    "music.youtube.com": "YouTube Music",
    "instagram.com":     "Instagram",
    "facebook.com":      "Facebook",
    "fb.watch":          "Facebook",
    "tiktok.com":        "TikTok",
    "vimeo.com":         "Vimeo",
    "twitter.com":       "Twitter/X",
    "x.com":             "Twitter/X",
    "twitch.tv":         "Twitch",
    "reddit.com":        "Reddit",
    "soundcloud.com":    "SoundCloud",
    "dailymotion.com":   "Dailymotion",
    "rumble.com":        "Rumble",
    "odysee.com":        "Odysee",
    "bilibili.com":      "Bilibili",
}

AUDIO_SITES = {"soundcloud.com", "music.youtube.com"}


def site_name(url: str) -> str:
    host = urlparse(url).hostname or ""
    host = host.lower().removeprefix("www.")
    for domain, name in SITE_MAP.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host or "Unknown"


def is_audio_site(url: str) -> bool:
    host = urlparse(url).hostname or ""
    host = host.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in AUDIO_SITES)


def fmt_size(b) -> str:
    if not b:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def fmt_dur(secs) -> str:
    if not secs:
        return ""
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def choose(prompt: str, options: list, allow_back: bool = False) -> int:
    """Numbered menu — returns 0-based index, or -1 for back."""
    print()
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    if allow_back:
        print("  0. Back")
    print()
    while True:
        try:
            raw = input(f"  {prompt}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(0)
        if allow_back and raw == "0":
            return -1
        try:
            val = int(raw)
            if 1 <= val <= len(options):
                return val - 1
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(options)}.")


# ── format analysis ───────────────────────────────────────────────────────────

def video_combined(formats: list) -> list:
    """Video+audio combined streams, deduplicated by height, highest first."""
    seen, result = set(), []
    fmts = [f for f in formats
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
            and f.get("height")]
    fmts.sort(key=lambda f: (f.get("height", 0), f.get("tbr") or 0), reverse=True)
    for f in fmts:
        if f["height"] not in seen:
            seen.add(f["height"])
            result.append(f)
    return result


def video_only(formats: list) -> list:
    """Video-only streams (no audio), deduplicated by height, highest first."""
    seen, result = set(), []
    fmts = [f for f in formats
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") in (None, "none")
            and f.get("height")]
    fmts.sort(key=lambda f: (f.get("height", 0), f.get("vbr") or f.get("tbr") or 0), reverse=True)
    for f in fmts:
        if f["height"] not in seen:
            seen.add(f["height"])
            result.append(f)
    return result


def audio_only(formats: list) -> list:
    """Audio-only streams, highest bitrate first."""
    fmts = [f for f in formats
            if f.get("vcodec") in (None, "none")
            and f.get("acodec") not in (None, "none")]
    fmts.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
    return fmts


def has_images(info: dict) -> bool:
    IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
    if info.get("ext") in IMAGE_EXTS:
        return True
    formats = info.get("formats") or []
    return any(f.get("ext") in IMAGE_EXTS for f in formats)


# ── progress ──────────────────────────────────────────────────────────────────

def make_progress_hook():
    state = {"last_pct": -1}

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta")

            pct = downloaded / total * 100 if total else 0
            if abs(pct - state["last_pct"]) < 0.5:
                return
            state["last_pct"] = pct

            filled = int(30 * pct / 100)
            bar = "█" * filled + "░" * (30 - filled)
            speed_str = (fmt_size(speed) + "/s") if speed else "?/s"
            eta_str = fmt_dur(eta) if eta else "?"
            print(f"\r  [{bar}] {pct:>5.1f}%  {speed_str:>10}  ETA {eta_str:>7}", end="", flush=True)

        elif d["status"] == "finished":
            print()

    return hook


# ── download ──────────────────────────────────────────────────────────────────

def base_opts(output_dir: str) -> dict:
    return {
        "outtmpl":        str(Path(output_dir) / "%(title)s.%(ext)s"),
        "quiet":          True,
        "no_warnings":    True,
        "progress_hooks": [make_progress_hook()],
    }


def do_download(url: str, opts: dict):
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


# ── menus ─────────────────────────────────────────────────────────────────────

def menu_quality(url: str, candidates: list, output_dir: str) -> dict | None:
    """Returns yt-dlp opts for the chosen quality, or None to go back."""
    q_labels = []
    for f in candidates:
        h       = f.get("height", "?")
        ext     = f.get("ext", "")
        fps     = int(f.get("fps") or 0)
        size    = fmt_size(f.get("filesize") or f.get("filesize_approx"))
        vcodec  = (f.get("vcodec") or "").split(".")[0]
        label   = f"{h}p"
        if fps > 30:
            label += f"@{fps}"
        label += f"  [{ext}"
        if vcodec:
            label += f"/{vcodec}"
        label += "]"
        if size != "?":
            label += f"  ~{size}"
        q_labels.append(label)

    q_idx = choose("Video quality", q_labels, allow_back=True)
    if q_idx == -1:
        return None

    fmt_id = candidates[q_idx]["format_id"]

    a_options = [
        ("best",    "Best available audio  (keep original codec)"),
        ("mp3",     "MP3  (re-encode to 192kbps)"),
        ("no_audio","No audio  (video only)"),
    ]
    a_idx = choose("Audio", [l for _, l in a_options], allow_back=True)
    if a_idx == -1:
        return None
    a_key = a_options[a_idx][0]

    opts = base_opts(output_dir)
    if a_key == "no_audio":
        opts["format"] = fmt_id
    else:
        opts["format"] = f"{fmt_id}+bestaudio/best"
        opts["merge_output_format"] = "mp4"
        if a_key == "mp3":
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]

    return opts


def menu_audio(formats: list, output_dir: str) -> dict:
    a_fmts = audio_only(formats)
    if a_fmts:
        hints = []
        for f in a_fmts[:3]:
            codec = f.get("acodec", "?")
            br    = f.get("abr") or f.get("tbr")
            hints.append(f"{codec} {int(br)}kbps" if br else codec)
        print(f"\n  Available source: {', '.join(hints)}")

    fmt_keys = [
        ("mp3_192",  "MP3  192kbps"),
        ("mp3_320",  "MP3  320kbps"),
        ("m4a",      "M4A  (best, AAC)"),
        ("opus",     "Opus  (best quality)"),
        ("wav",      "WAV  (lossless, large file)"),
        ("original", "Keep original codec  (no re-encoding)"),
    ]
    idx   = choose("Audio format", [l for _, l in fmt_keys])
    f_key = fmt_keys[idx][0]

    opts = base_opts(output_dir)
    opts["format"] = "bestaudio/best"

    pp_map = {
        "mp3_192": {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",  "preferredquality": "192"},
        "mp3_320": {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",  "preferredquality": "320"},
        "m4a":     {"key": "FFmpegExtractAudio", "preferredcodec": "m4a",  "preferredquality": "0"},
        "opus":    {"key": "FFmpegExtractAudio", "preferredcodec": "opus", "preferredquality": "0"},
        "wav":     {"key": "FFmpegExtractAudio", "preferredcodec": "wav",  "preferredquality": "0"},
    }
    if f_key in pp_map:
        opts["postprocessors"] = [pp_map[f_key]]

    return opts


# ── main flow ─────────────────────────────────────────────────────────────────

def run(url: str, output_dir: str):
    print("\nAnalyzing...")

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    site      = site_name(url)
    title     = info.get("title") or "Unknown"
    duration  = fmt_dur(info.get("duration"))
    is_playlist = info.get("_type") in ("playlist", "multi_video")

    print(f"\n  Site    : {site}")
    print(f"  Title   : {title}")
    if duration:
        print(f"  Duration: {duration}")

    # ── playlist ──────────────────────────────────────────────────────────────
    if is_playlist:
        entries = [e for e in (info.get("entries") or []) if e]
        print(f"  Items   : {len(entries)}")

        pl_options = [
            ("best_video", f"Download all  ({len(entries)} items) — best quality video"),
            ("audio_only", f"Download all  ({len(entries)} items) — audio only"),
            ("cancel",     "Cancel"),
        ]
        pl_idx    = choose("Playlist options", [l for _, l in pl_options])
        pl_action = pl_options[pl_idx][0]

        if pl_action == "cancel":
            print("\nCancelled.")
            sys.exit(0)

        if pl_action == "best_video":
            opts = base_opts(output_dir)
            opts["outtmpl"]             = str(Path(output_dir) / "%(playlist_index)s - %(title)s.%(ext)s")
            opts["format"]              = "bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"
        else:
            opts = menu_audio(info.get("formats") or [], output_dir)
            opts["outtmpl"] = str(Path(output_dir) / "%(playlist_index)s - %(title)s.%(ext)s")

        print(f"\nDownloading {len(entries)} items → {output_dir}")
        do_download(url, opts)
        print(f"\nDone! Saved to: {output_dir}\n")
        return

    # ── single content ────────────────────────────────────────────────────────
    formats    = info.get("formats") or []
    v_comb     = video_combined(formats)
    v_vid      = video_only(formats)
    has_vid    = bool(v_comb or v_vid)
    has_aud    = bool(audio_only(formats)) or has_vid
    has_img    = has_images(info)
    audio_site = is_audio_site(url)

    # Smart default menu order: audio-focused sites show audio first
    options = []
    if has_vid and not audio_site:
        options.append(("best_video",   "Video + Audio  (best quality)"))
        options.append(("pick_quality", "Video  —  choose quality"))
    if has_aud:
        options.append(("audio_only",   "Audio only"))
    if has_vid and audio_site:
        options.append(("best_video",   "Video + Audio  (best quality)"))
        options.append(("pick_quality", "Video  —  choose quality"))
    if has_img:
        options.append(("images",       "Download images / photos"))
    options.append(("cancel", "Cancel"))

    labels = [label for _, label in options]
    idx    = choose("What do you want to download?", labels)
    action = options[idx][0]

    if action == "cancel":
        print("\nCancelled.")
        sys.exit(0)

    if action == "best_video":
        opts = base_opts(output_dir)
        opts["format"]              = "bestvideo+bestaudio/best"
        opts["merge_output_format"] = "mp4"
        print(f"\nDownloading best quality → {output_dir}")
        do_download(url, opts)

    elif action == "pick_quality":
        candidates = v_comb or v_vid
        while True:
            opts = menu_quality(url, candidates, output_dir)
            if opts is not None:
                break
            # user pressed back — re-run top menu
            return run(url, output_dir)
        print(f"\nDownloading → {output_dir}")
        do_download(url, opts)

    elif action == "audio_only":
        opts = menu_audio(formats, output_dir)
        print(f"\nDownloading audio → {output_dir}")
        do_download(url, opts)

    elif action == "images":
        opts = base_opts(output_dir)
        opts["format"] = "best"
        print(f"\nDownloading images → {output_dir}")
        do_download(url, opts)

    print(f"\nDone! Saved to: {output_dir}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Download videos, audio, or images from YouTube, Instagram, TikTok, Vimeo and more.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python download.py https://youtube.com/watch?v=...
  python download.py https://www.instagram.com/p/...
  python download.py https://www.tiktok.com/@user/video/... -o ~/Downloads
        """,
    )
    parser.add_argument("url", help="URL to download")
    parser.add_argument("-o", "--output", default=".", metavar="DIR",
                        help="Output directory (default: current directory)")
    args = parser.parse_args()

    out = str(Path(args.output).expanduser().resolve())
    os.makedirs(out, exist_ok=True)

    try:
        run(args.url, out)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)


if __name__ == "__main__":
    main()
