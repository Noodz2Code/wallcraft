from wallcraft.library import Kind, classify, is_live, scan


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_classify():
    assert classify("a.JPG") is Kind.IMAGE
    assert classify("a.webp") is Kind.IMAGE
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
