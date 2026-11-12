import struct

from wallcraft.library import VIDEO_EXTS, Kind, classify, is_animated_webp, is_live, scan


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def webp_header(animated: bool) -> bytes:
    flags = 0x02 if animated else 0x00
    vp8x = b"VP8X" + struct.pack("<I", 10) + bytes([flags, 0, 0, 0]) + b"\x00" * 6
    body = b"WEBP" + vp8x
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_classify():
    assert classify("a.JPG") is Kind.IMAGE
    assert classify("missing.webp") is Kind.IMAGE  # unreadable WebP: treat as a still image
    assert classify("a.mp4") is Kind.VIDEO
    assert classify("a.gif") is Kind.ANIMATED
    assert classify("a.txt") is None
    assert is_live("x.webm") and not is_live("x.png")


def test_scan_recursive_dedupes_and_excludes(tmp_path):
    a = touch(tmp_path / "walls" / "b.jpg")
    touch(tmp_path / "walls" / "A.png")
    touch(tmp_path / "walls" / "sub" / "c.mp4")
    touch(tmp_path / "walls" / "notes.txt")
    touch(tmp_path / "walls" / ".hidden" / "d.jpg")
    excluded = touch(tmp_path / "walls" / "sub" / "skip.gif")
    extra = touch(tmp_path / "other" / "e.gif")

    items = scan(
        [str(tmp_path / "walls")],
        files=[str(extra), str(a)],
        excluded=[str(excluded)],
    )
    names = [i.name for i in items]
    assert names == ["A", "b", "c", "e"]
    assert [i.kind for i in items] == [Kind.IMAGE, Kind.IMAGE, Kind.VIDEO, Kind.ANIMATED]


def test_scan_non_recursive(tmp_path):
    touch(tmp_path / "a.jpg")
    touch(tmp_path / "sub" / "b.jpg")
    assert [i.name for i in scan([str(tmp_path)], recursive=False)] == ["a"]


def test_scan_missing_folder(tmp_path):
    assert scan([str(tmp_path / "missing")], files=[str(tmp_path / "gone.jpg")]) == []


def test_common_video_containers_are_live():
    for ext in (".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".flv", ".mpg", ".m2ts", ".3gp", ".ogv"):
        assert ext in VIDEO_EXTS
        assert classify(f"clip{ext.upper()}") is Kind.VIDEO


def test_webp_animation_is_detected_from_contents(tmp_path):
    animated = tmp_path / "loop.webp"
    animated.write_bytes(webp_header(animated=True))
    still = tmp_path / "photo.webp"
    still.write_bytes(webp_header(animated=False))
    simple = tmp_path / "simple.webp"  # lossy WebP without the extended header is never animated
    simple.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16)
    assert is_animated_webp(animated.read_bytes())
    assert classify(animated) is Kind.ANIMATED and is_live(str(animated))
    assert classify(still) is Kind.IMAGE
    assert classify(simple) is Kind.IMAGE


def test_ts_is_video_only_for_real_transport_streams(tmp_path):
    video = tmp_path / "recording.ts"
    video.write_bytes(bytes([0x47]) + b"\x00" * 187 + bytes([0x47]))
    code = tmp_path / "index.ts"
    code.write_text("export const x: number = 1;\n")
    assert classify(video) is Kind.VIDEO
    assert classify(code) is None
    assert [i.name for i in scan([str(tmp_path)])] == ["recording"]
