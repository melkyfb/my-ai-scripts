#!/usr/bin/env python3
"""
Transcribe audio/video files using OpenAI Whisper (local or API).

Requires:
    pip install openai-whisper          # local mode (default)
    pip install openai                  # only for --api mode
    System: ffmpeg must be installed    # apt install ffmpeg / brew install ffmpeg

Usage:
    python transcribe.py <file> [options]

    python transcribe.py interview.mp3
    python transcribe.py lecture.mp4 --srt --lang pt
    python transcribe.py clip.mov --model large --output result
    python transcribe.py audio.wav --api --api-key sk-...
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORTED = {'.mp3', '.mp4', '.mov', '.ogg', '.wav', '.m4a', '.webm', '.mkv'}


def check_ffmpeg():
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
    if result.returncode != 0:
        print("Error: ffmpeg not found. Install it: apt install ffmpeg / brew install ffmpeg",
              file=sys.stderr)
        sys.exit(1)


def clean_audio(input_path: Path, tmp_dir: str) -> str:
    """Convert to 16kHz mono WAV and apply noise reduction + loudness normalization."""
    out = os.path.join(tmp_dir, 'cleaned.wav')
    cmd = [
        'ffmpeg', '-i', str(input_path),
        '-ac', '1',
        '-ar', '16000',
        '-af', 'afftdn=nf=-25,loudnorm',
        '-y', out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return out


def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list) -> str:
    blocks = []
    for i, seg in enumerate(segments, 1):
        start = format_srt_time(seg['start'])
        end = format_srt_time(seg['end'])
        text = seg['text'].strip()
        blocks.append(f"{i}\n{start} --> {end}\n{text}")
    return '\n\n'.join(blocks) + '\n'


def transcribe_local(audio_path: str, model_name: str, language: str | None) -> dict:
    try:
        import whisper
    except ImportError:
        print("Error: openai-whisper not installed. Run: pip install openai-whisper",
              file=sys.stderr)
        sys.exit(1)

    print(f"Loading model '{model_name}'...")
    model = whisper.load_model(model_name)
    print("Transcribing...")
    return model.transcribe(audio_path, language=language, verbose=False)


def transcribe_api(audio_path: str, language: str | None, api_key: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        print("Error: openai not installed. Run: pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    print("Transcribing via OpenAI API...")

    with open(audio_path, 'rb') as f:
        kwargs = dict(model='whisper-1', file=f, response_format='verbose_json')
        if language:
            kwargs['language'] = language
        response = client.audio.transcriptions.create(**kwargs)

    segments = [
        {'start': s.start, 'end': s.end, 'text': s.text}
        for s in (response.segments or [])
    ]
    return {'text': response.text, 'segments': segments}


def main():
    parser = argparse.ArgumentParser(
        description='Transcribe audio/video to TXT and optionally SRT'
    )
    parser.add_argument('file', help='Input file (mp3, mp4, mov, ogg, wav, m4a)')
    parser.add_argument('-o', '--output',
                        help='Output base name without extension (default: same as input)')
    parser.add_argument('--srt', action='store_true',
                        help='Also generate SRT subtitle file with timestamps')
    parser.add_argument('--lang', metavar='CODE',
                        help='Language code: pt, en, es, fr... (auto-detected if omitted)')
    parser.add_argument('--model', default='medium',
                        choices=['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3'],
                        help='Whisper model size (default: medium). Larger = slower + more accurate')
    parser.add_argument('--no-clean', action='store_true',
                        help='Skip audio cleaning step')
    parser.add_argument('--api', action='store_true',
                        help='Use OpenAI Whisper API instead of local model')
    parser.add_argument('--api-key', metavar='KEY',
                        help='OpenAI API key (or set OPENAI_API_KEY env var)')
    args = parser.parse_args()

    input_path = Path(args.file).resolve()
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if input_path.suffix.lower() not in SUPPORTED:
        print(f"Warning: '{input_path.suffix}' not in known supported types — trying anyway.")

    output_base = Path(args.output).resolve() if args.output else input_path.with_suffix('')

    check_ffmpeg()

    with tempfile.TemporaryDirectory() as tmp:
        if args.no_clean:
            audio_path = str(input_path)
        else:
            print("Cleaning audio...")
            audio_path = clean_audio(input_path, tmp)

        if args.api:
            key = args.api_key or os.environ.get('OPENAI_API_KEY')
            if not key:
                print("Error: --api requires --api-key or OPENAI_API_KEY env var", file=sys.stderr)
                sys.exit(1)
            result = transcribe_api(audio_path, args.lang, key)
        else:
            result = transcribe_local(audio_path, args.model, args.lang)

    txt_path = output_base.with_suffix('.txt')
    txt_path.write_text(result['text'].strip(), encoding='utf-8')
    print(f"Transcription → {txt_path}")

    if args.srt:
        segments = result.get('segments') or []
        if not segments:
            print("Warning: no segment timestamps available — SRT not generated.")
        else:
            srt_path = output_base.with_suffix('.srt')
            srt_path.write_text(segments_to_srt(segments), encoding='utf-8')
            print(f"Subtitles     → {srt_path}")


if __name__ == '__main__':
    main()
