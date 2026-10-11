"""DF listing evidence: primary cards and observed archive navigation."""
from html.parser import HTMLParser
import re


class DfListing(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.primary_links = []
        self.pagination = []
        self.has_primary_layout = False
        self.anchor = None
        self.card = None
        self.primary_cards = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in ('meta', 'link', 'br', 'img', 'input', 'hr', 'source', 'wbr'):
            self.stack.append((tag, attrs.get('class', '').split()))
        classes = {c for _, names in self.stack for c in names}
        primary = ('card__content' in classes and ('g-lg-9' in classes or 'tax-list' in classes)
                   and not classes.intersection(('tabs', 'tab-content', 'menu', 'newsletter')))
        self.has_primary_layout |= primary or 'tax-list' in classes
        if tag=='article':self.card={'links':[],'text':[],'primary':False}
        if tag == 'a':
            self.anchor = (attrs.get('href'), [], primary, 'wp-pagenavi' in classes)

    def handle_data(self, data):
        if self.anchor:
            self.anchor[1].append(data)
        if self.card:self.card['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor:
            href, parts, primary, navigation = self.anchor
            value = (href, ' '.join(''.join(parts).split()))
            if primary:
                self.primary_links.append(value)
                if self.card:
                    self.card['links'].append(value)
                    self.card['primary']=True
            if navigation:
                self.pagination.append(value)
            self.anchor = None
        if tag=='article' and self.card:
            if self.card['primary']:
                day=re.search(r'\b(\d{2})/(\d{2})/(20\d{2})\b',' '.join(self.card['text']))
                self.primary_cards.append({'links':self.card['links'],
                                           'listing_day':f'{day[3]}-{day[2]}-{day[1]}' if day else None})
            self.card=None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
