import random

from wallcraft.slideshow import Slideshow


def test_sequential_cycles_in_order():
    s = Slideshow()
    s.configure(["a", "b", "c"], shuffle=False)
    assert s.current is None
    assert [s.next() for _ in range(4)] == ["a", "b", "c", "a"]
    assert s.previous() == "c"


def test_shuffle_visits_every_item_once_per_round():
    s = Slideshow(random.Random(1))
    items = [str(i) for i in range(10)]
    s.configure(items, shuffle=True)
    first_round = [s.next() for _ in range(10)]
    assert sorted(first_round) == sorted(items)
    second_round = [s.next() for _ in range(10)]
    assert sorted(second_round) == sorted(items)
    assert second_round[0] != first_round[-1]


def test_configure_keeps_current_position():
    s = Slideshow()
    s.configure(["a", "b", "c"], shuffle=False, current="b")
    assert s.current == "b"
    assert s.next() == "c"
    s.configure(["a", "b", "c", "d"], shuffle=False)
    assert s.current == "c"
    assert s.next() == "d"


def test_removed_current_resets():
    s = Slideshow()
    s.configure(["a", "b"], shuffle=False, current="b")
    s.configure(["a"], shuffle=False)
    assert s.current is None
    assert s.next() == "a"


def test_empty():
    s = Slideshow()
    s.configure([], shuffle=True)
    assert s.next() is None and s.previous() is None


def test_duplicates_are_ignored():
    s = Slideshow()
    s.configure(["a", "a", "b"], shuffle=False)
    assert [s.next() for _ in range(3)] == ["a", "b", "a"]
