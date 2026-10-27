"""Promo video encoding: JPEG frames on disk -> one movie file.

Two ways, best first:

  * ffmpeg (bundled, on PATH, Homebrew): H.264 MP4, yuv420p, +faststart -
    plays everywhere (browsers, phones, social sites).
  * macOS without ffmpeg (the app ships FreeCAD's libav libraries but not
    the ffmpeg program): write_mov() wraps the JPEG frames as they are in a
    QuickTime movie (Photo - JPEG, pure Python), and the system's own
    /usr/bin/avconvert turns that into H.264 MP4 (MEASURED macOS 26: it
    reads the movie; PresetHighestQuality gives H.264 High).
  * neither: the QuickTime movie itself (QuickTime Player, Quick Look,
    Keynote, iMovie play it; browsers do not).

No FreeCAD, no Qt: runs in the promo job's own process.
"""
import os
import shutil
import struct
import subprocess
import sys

FFMPEG_ENV = "ATECH_FFMPEG"


def find_ffmpeg():
    """An ffmpeg program, or None: $ATECH_FFMPEG, next to this Python (a
    bundle that ships one), PATH, then Homebrew's and the system's."""
    cands = [os.environ.get(FFMPEG_ENV),
             os.path.join(os.path.dirname(os.path.realpath(sys.executable or "")), "ffmpeg"),
             shutil.which("ffmpeg"),
             "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def ffmpeg_mp4(ffmpeg, frames_pattern, fps, out, timeout=900):
    """H.264 MP4 of frames_pattern (an ffmpeg %05d pattern). True when out
    was written."""
    argv = [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps),
            "-i", frames_pattern, "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", out]
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    if p.returncode != 0:
        # an ffmpeg without libx264: its default MP4 encoder
        i = argv.index("libx264")
        argv[i - 1:i + 5] = ["-q:v", "3"]
        try:
            p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return False
    return p.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0


# ------------------------------------------------------------ QuickTime
def _atom(kind, *payload):
    body = b"".join(payload)
    return struct.pack(">I4s", 8 + len(body), kind) + body


def _full(kind, version, flags, *payload):
    return _atom(kind, struct.pack(">I", (version << 24) | flags), *payload)


_MATRIX = struct.pack(">9I", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)


def _pascal(text, size=None):
    b = text.encode("ascii")[:31 if size else 255]
    out = bytes([len(b)]) + b
    if size:
        out = out.ljust(size, b"\0")
    return out


def write_mov(frames, fps, out, width, height):
    """QuickTime movie (Photo - JPEG) of the JPEG files `frames`, in order,
    at `fps`. Each JPEG goes in as it is. Returns out."""
    sizes = [os.path.getsize(f) for f in frames]
    n = len(frames)
    if not n:
        raise ValueError("no frames")
    media_scale, delta = int(round(fps * 100)), 100
    movie_scale = 1000
    dur_media = n * delta
    dur_movie = int(round(n * movie_scale / float(fps)))
    ftyp = _atom(b"ftyp", b"qt  ", struct.pack(">I", 0x200), b"qt  ")
    mdat_head = len(ftyp)
    offsets, pos = [], mdat_head + 8
    for s in sizes:
        offsets.append(pos)
        pos += s
    if pos > 0xFFFFFFFF:
        raise ValueError("movie too large for 32-bit offsets")
    stsd_entry = (b"\0" * 6 + struct.pack(">H", 1)              # data reference 1
                  + struct.pack(">HH4sII", 0, 0, b"appl", 0, 0x200)
                  + struct.pack(">HHII", width, height, 72 << 16, 72 << 16)
                  + struct.pack(">IH", 0, 1) + _pascal("Photo - JPEG", 32)
                  + struct.pack(">hh", 24, -1))
    stsd = _full(b"stsd", 0, 0, struct.pack(">I", 1),
                 struct.pack(">I4s", 8 + len(stsd_entry), b"jpeg") + stsd_entry)
    stts = _full(b"stts", 0, 0, struct.pack(">III", 1, n, delta))
    stsc = _full(b"stsc", 0, 0, struct.pack(">IIII", 1, 1, 1, 1))
    stsz = _full(b"stsz", 0, 0, struct.pack(">II", 0, n), struct.pack(">%dI" % n, *sizes))
    stco = _full(b"stco", 0, 0, struct.pack(">I", n), struct.pack(">%dI" % n, *offsets))
    stbl = _atom(b"stbl", stsd, stts, stsc, stsz, stco)
    vmhd = _full(b"vmhd", 0, 1, struct.pack(">HHHH", 0x40, 0x8000, 0x8000, 0x8000))
    dhlr = _full(b"hdlr", 0, 0, b"dhlr", b"alis", b"appl", struct.pack(">II", 0, 0),
                 _pascal("Data Handler"))
    dref = _full(b"dref", 0, 0, struct.pack(">I", 1), _full(b"alis", 0, 1))
    minf = _atom(b"minf", vmhd, dhlr, _atom(b"dinf", dref), stbl)
    mdhd = _full(b"mdhd", 0, 0, struct.pack(">IIIIHH", 0, 0, media_scale, dur_media, 0, 0))
    mhlr = _full(b"hdlr", 0, 0, b"mhlr", b"vide", b"appl", struct.pack(">II", 0, 0),
                 _pascal("Video Handler"))
    mdia = _atom(b"mdia", mdhd, mhlr, minf)
    tkhd = _full(b"tkhd", 0, 0xF, struct.pack(">IIIII", 0, 0, 1, 0, dur_movie),
                 b"\0" * 8, struct.pack(">hhhH", 0, 0, 0, 0), _MATRIX,
                 struct.pack(">II", width << 16, height << 16))
    trak = _atom(b"trak", tkhd, mdia)
    mvhd = _full(b"mvhd", 0, 0, struct.pack(">IIII", 0, 0, movie_scale, dur_movie),
                 struct.pack(">IH", 0x10000, 0x100), b"\0" * 10, _MATRIX,
                 struct.pack(">6I", 0, 0, 0, 0, 0, 0), struct.pack(">I", 2))
    moov = _atom(b"moov", mvhd, trak)
    tmp = out + ".part"
    with open(tmp, "wb") as fh:
        fh.write(ftyp)
        fh.write(struct.pack(">I4s", 8 + sum(sizes), b"mdat"))
        for f in frames:
            with open(f, "rb") as src:
                shutil.copyfileobj(src, fh)
        fh.write(moov)
    os.replace(tmp, out)
    return out


def encode(frames_dir, fps, out_base, width, height, ffmpeg=None):
    """frames_dir/00000.jpg ... -> out_base + ".mp4" (ffmpeg) or ".mov".
    Returns the path written."""
    frames = sorted(os.path.join(frames_dir, f) for f in os.listdir(frames_dir)
                    if f.endswith(".jpg"))
    if not frames:
        raise ValueError("no frames to encode")
    ffmpeg = find_ffmpeg() if ffmpeg is None else ffmpeg
    if ffmpeg:
        out = out_base + ".mp4"
        if ffmpeg_mp4(ffmpeg, os.path.join(frames_dir, "%05d.jpg"), fps, out):
            return out
    av = find_avconvert()
    if av:
        mov = write_mov(frames, fps, os.path.join(frames_dir, "movie.mov"), width, height)
        out = out_base + ".mp4"
        if avconvert_mp4(av, mov, out):
            return out
        shutil.move(mov, out_base + ".mov")
        return out_base + ".mov"
    return write_mov(frames, fps, out_base + ".mov", width, height)


AVCONVERT = "/usr/bin/avconvert"


def find_avconvert():
    """macOS's own movie converter, or None."""
    if sys.platform == "darwin" and os.access(AVCONVERT, os.X_OK):
        return AVCONVERT
    return None


def avconvert_mp4(avconvert, mov, out, timeout=900):
    """H.264 MP4 of a QuickTime movie via AVFoundation. True when written."""
    tmp = out + ".part.mp4"
    try:
        p = subprocess.run([avconvert, "--source", mov, "--preset", "PresetHighestQuality",
                            "--output", tmp, "--replace"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    if p.returncode != 0 or not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    os.replace(tmp, out)
    return True
