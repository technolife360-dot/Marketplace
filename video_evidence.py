"""Bounded private video evidence; never serve original uploaded files."""
import re
import subprocess
import tempfile
from pathlib import Path

MAX_BYTES=4*1024*1024

class InvalidVideo(ValueError):pass
class VideoUnavailable(RuntimeError):pass

def normalize(raw):
    if not 20<=len(raw)<=MAX_BYTES or raw[4:8]!=b'ftyp':raise InvalidVideo('Choose an MP4 video up to 4 MB and 30 seconds.')
    try:
        import imageio_ffmpeg
        executable=imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:raise VideoUnavailable('The video processor is not available.') from exc
    with tempfile.TemporaryDirectory(prefix='sentryloot-video-') as directory:
        source=Path(directory)/'input.mp4';target=Path(directory)/'normalized.mp4';source.write_bytes(raw)
        base=[executable,'-nostdin','-hide_banner','-protocol_whitelist','file,pipe','-max_alloc','33554432','-threads','1','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',str(source)]
        try:
            probe=subprocess.run(base,capture_output=True,timeout=3,check=False)
            details=probe.stderr.decode('utf-8','replace')
            duration=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',details)
            size=re.search(r'Video: [^\n]*?\b(\d{2,5})x(\d{2,5})\b',details)
            if not duration or not size:raise InvalidVideo('The video could not be decoded.')
            seconds=int(duration[1])*3600+int(duration[2])*60+float(duration[3]);width,height=map(int,size.groups())
            if not 0<seconds<=30 or width*height>4000000:raise InvalidVideo('Use a video up to 30 seconds and 4 megapixels.')
            command=base+['-loglevel','error','-map','0:v:0','-an','-map_metadata','-1','-vf','scale=960:960:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=15','-t','30','-c:v','libx264','-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart','-fs',str(MAX_BYTES),'-y',str(target)]
            result=subprocess.run(command,capture_output=True,timeout=8,check=False)
            if result.returncode or not target.is_file():raise InvalidVideo('The video could not be decoded. Try another MP4.')
            value=target.read_bytes()
            if not 20<=len(value)<=MAX_BYTES:raise InvalidVideo('The processed video is too large.')
            return value
        except subprocess.TimeoutExpired as exc:raise InvalidVideo('Video processing timed out. Use a shorter clip.') from exc
