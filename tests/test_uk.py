from datetime import datetime

from server.keys import RowFail, build_uk


def test_date_formats_share_uk():
    key = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    a = build_uk({"Date": "19-09-24", "Party Name": "Acme", "Sales Rep": "R", "Net Amount": "1234.5"}, key)
    b = build_uk({"Date": datetime(2024, 9, 19, 15, 30), "Party Name": "Acme", "Sales Rep": "R", "Net Amount": "1,234.50"}, key)
    assert a == b


def test_amounts_share_uk():
    key = ["Net Amount"]
    assert build_uk({"Net Amount": "1,234.50"}, key) == build_uk({"Net Amount": "1234.5"}, key)


def test_unparseable_date_fails_row():
    try:
        build_uk({"Date": "not-a-date", "Party Name": "A"}, ["Date"])
        assert False
    except RowFail:
        pass
