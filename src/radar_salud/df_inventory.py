"""DF listing evidence: primary cards and observed archive navigation."""
from html.parser import HTMLParser


class DfListing(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.primary_links = []
        self.pagination = []
        self.has_primary_layout = False
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in ('meta', 'link', 'br', 'img', 'input', 'hr', 'source', 'wbr'):
            self.stack.append((tag, attrs.get('class', '').split()))
        classes = {c for _, names in self.stack for c in names}
        primary = ('card__content' in classes and ('g-lg-9' in classes or 'tax-list' in classes)
                   and not classes.intersection(('tabs', 'tab-content', 'menu', 'newsletter')))
        self.has_primary_layout |= primary or 'tax-list' in classes
        if tag == 'a':
            self.anchor = (attrs.get('href'), [], primary, 'wp-pagenavi' in classes)

    def handle_data(self, data):
        if self.anchor:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor:
            href, parts, primary, navigation = self.anchor
            value = (href, ' '.join(''.join(parts).split()))
            if primary:
                self.primary_links.append(value)
            if navigation:
                self.pagination.append(value)
            self.anchor = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
