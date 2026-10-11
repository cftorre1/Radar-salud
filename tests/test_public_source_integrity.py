from datetime import date
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from radar_salud.models import RawItem
from radar_salud.public_source_evidence import (
    discovery_diagnostics, failure_details, verified_publication,
)
from radar_salud import public_source_transport as transport


def item(slug="fonasa", url="https://www.fonasa.gob.cl/noticias/cobertura/"):
    return RawItem(slug,"Publicación oficial verificable",url,"Fuente oficial","official",
                   event_date="2026-09-24",metadata={
                       "publication_date_source":"article:published_time",
                       "publication_date_evidence":{"kind":"article:published_time",
                           "value":"2026-09-24T09:00:00-03:00","date":"2026-09-24","url":url}})


@pytest.mark.parametrize("value",["Período 2026-09-24 sin fecha de publicación",
    "2026-09-24/2026-10-01", "2026-02-31", "2026-09-24T28:00:00Z", "2026-09-23"])
def test_publication_guard_rejects_periods_invalid_fields_and_disagreement(value):
    raw=item();raw.metadata["publication_date_evidence"]["value"]=value
    assert not verified_publication(raw,today=date(2026,10,11))


def test_detail_evidence_must_belong_to_same_article_and_calendar():
    raw=item()
    assert verified_publication(raw,today=date(2026,10,11))
    assert not verified_publication(raw,today=date(2026,9,23))
    raw.metadata["publication_date_evidence"]["url"]="https://www.fonasa.gob.cl/noticias/another/"
    assert not verified_publication(raw,today=date(2026,10,11))


def test_listing_evidence_bound_to_surface_not_pdf_upload_directory():
    raw=item("deis","https://repositoriodeis.minsal.cl/uploads/2021/03/guidance-junio2026.pdf")
    kind="official_document_listing:published";listing="https://deis.minsal.cl/centrofic/"
    raw.event_date="2026-06-25"
    raw.metadata.update(discovered_from=listing,publication_date_source=kind,
        publication_date_evidence={"kind":kind,"value":"Publicado 25/06/2026",
            "date":"2026-06-25","url":listing})
    assert verified_publication(raw,today=date(2026,10,11))
    raw.metadata["publication_date_evidence"]["url"]="https://deis.minsal.cl/other/"
    assert not verified_publication(raw,today=date(2026,10,11))


@pytest.mark.parametrize("url",["http://www.ispch.cl/pdf", "https://evil.example/pdf",
    "https://www.ispch.cl.evil.example/pdf", "https://user@www.ispch.cl/pdf"])
def test_redirect_rejected_before_request_to_unverified_destination(url):
    handler=transport.OfficialRedirectHandler("isp_surveillance")
    with pytest.raises(ValueError,match="redirect"):
        handler.redirect_request(Request("https://www.ispch.cl/boletin/"),None,302,"Found",{},url)


def test_redirect_between_official_aliases_is_permitted():
    req=transport.OfficialRedirectHandler("isp_surveillance").redirect_request(
        Request("https://www.ispch.gob.cl/boletin/"),None,301,"Moved",{},"https://www.ispch.cl/boletin/")
    assert req.full_url=="https://www.ispch.cl/boletin/"


def test_unexpected_final_url_or_oversize_capture_fails_closed(monkeypatch):
    class Response:
        headers=Message()
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def geturl(self):return "https://evil.example/forged"
        def read(self,*args):raise AssertionError("untrusted content must not be read")
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(transport,"build_opener",lambda *a:Opener())
    with pytest.raises(ValueError,match="response"):
        transport.download_official("https://deis.minsal.cl/centrofic/","deis")
    Response.geturl=lambda self:"https://deis.minsal.cl/centrofic/"
    Response.read=lambda self,*args:b"abcdef"
    with pytest.raises(ValueError,match="byte limit"):
        transport.download_official("https://deis.minsal.cl/centrofic/","deis",max_bytes=5)


def test_pdf_cannot_be_a_successful_html_block_page(monkeypatch):
    monkeypatch.setattr(transport,"download_official",lambda *a,**kw:(b"<html>403</html>",Message()))
    with pytest.raises(ValueError,match="not a PDF"):
        transport.extract_public_source_pdf("https://www.ispch.cl/report.pdf","isp_surveillance")


def test_exact_error_chain_retains_status_and_proxy_cause_without_query():
    http=HTTPError("https://deis.minsal.cl/centrofic/?token=private",403,"Forbidden",None,None)
    assert failure_details(http)["exception_chain"][0]["url"]=="https://deis.minsal.cl/centrofic/"
    proxy=URLError("Tunnel connection failed: 403 Forbidden")
    outer=RuntimeError("listing unavailable");outer.__cause__=proxy
    assert "403 Forbidden" in failure_details(outer)["failure_signature"]


def test_diagnostics_preserve_failed_fronts_and_zero_verified_candidates():
    class Scout:
        diagnostics=[{"url":"https://www.ispch.cl/boletin/","status":"blocked","error_type":"URLError"}]
    raw=item();raw.metadata.clear()
    result=discovery_diagnostics(Scout(),[raw])
    assert result["partial_failure"] and result["verified_publications"]==0
