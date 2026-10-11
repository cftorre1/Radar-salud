"""Small HTML table reader shared by official, public data adapters."""
from html.parser import HTMLParser
import re
import unicodedata


def fold(text):
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', str(text))
                                      if not unicodedata.combining(c))).casefold().strip()


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows = []; self.row = None; self.cell = None
        self.text = []; self.links = []; self.href = None; self.label = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr': self.row = []
        if tag in ('td', 'th') and self.row is not None: self.cell = []
        if tag == 'a': self.href = attrs.get('href'); self.label = []

    def handle_data(self, value):
        self.text.append(value)
        if self.cell is not None: self.cell.append(value)
        if self.href is not None: self.label.append(value)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell = None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row); self.row = None
        if tag == 'a' and self.href is not None:
            self.links.append((self.href, ' '.join(''.join(self.label).split()))); self.href = None


def read(html):
    parser = Tables(); parser.feed(html); return parser
