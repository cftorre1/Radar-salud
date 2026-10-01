from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urljoin, urlparse

from .beta_sources import CuratedBetaSourceScout, _Links
from .scouts import fetch_html


class FastCuratedBetaSourceScout(CuratedBetaSourceScout):
    """Runtime validator: inspect only the newest bounded set from each approved listing."""

    MAX_DETAILS=5

    def discover(self):
        page_html=fetch_html(self.cfg["page"])
        parser=_Links();parser.feed(page_html)
        selected=[];seen=set()
        for href,title in parser.links:
            if not href:
                continue
            url=urljoin(self.cfg["page"],href);parsed=urlparse(url)
            if parsed.scheme!="https" or parsed.netloc not in self.cfg["hosts"]:
                continue
            if not re.fullmatch(self.cfg["path"],parsed.path) or url in seen:
                continue
            seen.add(url)
            selected.append((url,title))
            if len(selected)>=self.MAX_DETAILS:
                break
        mini="".join(f'<a href="{html_lib.escape(url,quote=True)}">{html_lib.escape(title)}</a>' for url,title in selected)
        return super().discover_from_html(mini,detail_loader=fetch_html)
