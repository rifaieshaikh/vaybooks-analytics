"""Load Excel/CSV into header+rows without going through Table required-columns."""

from io import BytesIO

from vay.dates import clean_text
from vay.load import _read_frame


def frames_from_bytes(data, filename=""):
    return _read_frame(BytesIO(data), filename)


def frame_values(frame):
    if frame is None or frame.empty:
        headers = [clean_text(h) for h in list(frame.columns)] if frame is not None else []
        return headers, []
    headers = [clean_text(h) for h in list(frame.columns)]
    rows = []
    for values in frame.itertuples(index=False, name=None):
        rows.append(list(values))
    return headers, rows
