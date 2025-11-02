import pytest

from qmtl.foundation.common.tagquery import split_tags


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, []),
        ("", []),
        (",,,", []),
        ("t1,t2", ["t1", "t2"]),
        (" t1 ,  t2\t,\n t3 ", ["t1", "t2", "t3"]),
    ],
)
def test_split_tags_from_string(raw, expected):
    assert split_tags(raw) == expected


def test_split_tags_from_iterable_trims_and_filters():
    tags = [" t1 ", "t2", "", "  ", "t3"]
    assert split_tags(tags) == ["t1", "t2", "t3"]


def test_split_tags_from_iterable_non_string_items():
    tags = [" t1", 2, None]
    # Non-string entries are coerced via str() and trimmed
    assert split_tags(tags) == ["t1", "2", "None"]
