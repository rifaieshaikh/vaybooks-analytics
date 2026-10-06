class MissingColumnsError(Exception):
    def __init__(self, sheet, missing):
        self.sheet = sheet
        self.missing = missing
        super().__init__("%s is missing columns: %s" % (sheet, ", ".join(missing)))


class Table:
    def __init__(self, name, headers, rows, error=None):
        self.name = name
        self.headers = list(headers)
        self.rows = rows
        self.error = error
        self.index = {}
        for i, h in enumerate(self.headers):
            if h and h not in self.index:
                self.index[h] = i

    def col(self, header):
        return self.index[header]

    def get(self, row, header, default=""):
        i = self.index.get(header)
        if i is None or i >= len(row):
            return default
        return row[i]
