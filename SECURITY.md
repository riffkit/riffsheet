# Security

riffsheet passes the video files you give it to ffmpeg and ffprobe, which parse them. Treat a video from an untrusted source as you would any untrusted file, and keep ffmpeg up to date: a vulnerability in ffmpeg's own decoders belongs to the FFmpeg project (https://ffmpeg.org/security.html).

The tool runs ffmpeg with argument lists, never through a shell, and uses no network; only `transcribe --download` fetches a speech model.

To report a vulnerability in riffsheet itself, use GitHub's private reporting (the repository's Security tab, "Report a vulnerability") rather than a public issue. We will reply there.
