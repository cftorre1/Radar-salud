"""Factual pulse from three reconciled official workbook families; fail closed."""
from datetime import date, datetime
from urllib.parse import urlparse
import re

from .isapre_insights import derive


RELEASE_URLS = {
    "cartera": "https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/",
    "suscripciones": "https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-suscripciones-y-desahucios-del-sistema-isapre-ano-2026/",
    "movilidad": "https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-movilidad-de-cartera-de-cotizantes-del-sistema-isapre-a-nivel-regional-ano-2026/",
}


def _count(value):
    if not isinstance(value,int) or isinstance(value,bool) or value<0:
        raise ValueError("Invalid count")
    return value


def _release_family(item):
    title=str(item.get("title") or "").lower()
    if "2026" not in title:
        return None
    if "movilidad" in title and "cartera de cotizantes" in title:
        return "movilidad"
    if "suscripciones" in title and "desahucios" in title:
        return "suscripciones"
    if "cartera de beneficiarios" in title and "nivel regional" not in title:
        return "cartera"
    return None


def _official_releases(items):
    selected={}
    for item in items or []:
        family=_release_family(item)
        if not family:continue
        source=urlparse(item.get("source_url") or "")
        if (item.get("source_name")!="Superintendencia de Salud" or item.get("source_type")!="official"
                or source.scheme!="https" or source.netloc!="www.superdesalud.gob.cl"
                or item.get("source_url") != RELEASE_URLS[family]):
            continue
        published=date.fromisoformat(item["event_date"])
        candidate={"family":family,"title":item["title"],"source_name":item["source_name"],
                   "url":item["source_url"],"event_date":published.isoformat()}
        if family not in selected or published>date.fromisoformat(selected[family]["event_date"]):
            selected[family]=candidate
    if set(selected)!={"cartera","suscripciones","movilidad"}:
        raise ValueError("Missing official release evidence")
    if len({item["url"] for item in selected.values()}) != len(RELEASE_URLS):
        raise ValueError("Release evidence is not unique")
    return selected


def build_pulse(validation, releases=None):
    try:
        families=validation["families"]
        car,sub,mob=(families[k] for k in ("cartera","suscripciones","movilidad"))
        for item in (car,sub,mob):
            if item["status"]!="validated" or not re.fullmatch(r"[0-9a-f]{64}",item["sha256"]) or not item["series"]:
                raise ValueError("Unvalidated workbook")
            u=urlparse(item["source_url"])
            if u.scheme!="https" or u.netloc!="www.superdesalud.gob.cl":
                raise ValueError("Unexpected source")
        c,s,m=(item["series"][-1] for item in (car,sub,mob))
        period=c["period"]
        if s["period"]!=period or m["period_end"]!=period or m["period_type"]!="comparison_between_july_cuts":
            raise ValueError("Incomparable periods")
        start=date.fromisoformat(m["period_start"]+"-01")
        end=date.fromisoformat(period+"-01")
        if start>=end:raise ValueError("Invalid mobility interval")
        official=_official_releases(releases)
        publication_date=max(date.fromisoformat(x["event_date"]) for x in official.values())
        validated_at=datetime.fromisoformat(validation["validated_at"].replace("Z","+00:00"))
        today=date.today()
        if publication_date>today or validated_at.date()>today or validated_at.date()<publication_date:
            raise ValueError("Validation predates publication")
        cm,sm,mm=c["metrics"],s["metrics"],m["metrics"]
        cot,cargas,benef=(_count(cm[k]) for k in ("cotizantes","cargas","beneficiarios"))
        contracts,voluntary=(_count(sm[k]) for k in ("contratos_suscritos","desahucios_voluntarios"))
        exits,entries=(_count(mm[k]) for k in ("salidas_intervalo","entradas_intervalo"))
        net=mm["diferencia_intervalo"]
        if not isinstance(net,int) or isinstance(net,bool) or cot+cargas!=benef or entries-exits!=net:
            raise ValueError("Unreconciled totals")
        analytic=derive(validation)
        if analytic["status"]!="validated":
            raise ValueError("Unvalidated analytic series")
        business=analytic["business_metrics"]
        decline=_count(business["beneficiary_decline"])
        cargas_decline=_count(business["cargas_decline"])
        streak=_count(business["consecutive_monthly_beneficiary_declines"])
        cargas_share=business["cargas_share_of_decline_pct"]
        if decline<=0 or cargas_decline<=0 or streak<2 or not isinstance(cargas_share,(int,float)) or isinstance(cargas_share,bool):
            raise ValueError("Business reading is not supported by current series")
        share_label=f"{cargas_share:.1f}".replace(".",",")
        by_kind={item["analysis_kind"]:item for item in analytic["insights"]}
        selected_kinds=("beneficiary_stock_change","portfolio_mix_shift","beneficiary_streak",
                        "subscriptions_voluntary_gap","mobility_interval")
        published_insights=[by_kind[kind] for kind in selected_kinds]
        label=lambda v:f"{v:,}".replace(",",".")
        start_label=start.strftime("%m-%Y");end_label=end.strftime("%m-%Y")
        return {
            "title":f"Pulso Isapre · datos a {period}","source_name":"Superintendencia de Salud",
            "source_type":"official","source_url":official["cartera"]["url"],
            "event_date":publication_date.isoformat(),"publication_date":publication_date.isoformat(),
            "validation_date":validated_at.date().isoformat(),"data_period":period,
            "signal_types":["Datos"],"scopes":["Isapres"],"ingestion_mode":"BACKFILL",
            "category":"Datos sectoriales","event_type":"DATA_PULSE","distribution":"archive",
            "radar_score":72,"confidence_score":100,
            "what_happened":f"Las series oficiales del sistema Isapre registran a {period} una cartera de {label(benef)} beneficiarios ({label(cot)} cotizantes y {label(cargas)} cargas).",
            "why_it_matters":f"La cartera acumula {streak} bajas mensuales y {label(decline)} beneficiarios menos entre enero y julio; {share_label}% de esa disminución aritmética corresponde a cargas. Para gestión comercial y financiera, es una alerta de composición y base de ingresos, no una explicación causal: la brecha entre contratos y desahucios voluntarios omite otras terminaciones, y la movilidad usa otro intervalo. Conviene seguir terminaciones completas, mezcla de cartera y próximas publicaciones antes de atribuir desempeño.",
            "key_points":[f"En {period} se registraron {label(contracts)} contratos suscritos y {label(voluntary)} desahucios voluntarios; estos últimos no representan todas las terminaciones.",
                f"Entre los cortes {start_label} y {end_label} se registraron {label(exits)} salidas y {label(entries)} entradas por movilidad; diferencia entradas menos salidas: {label(net)}."],
            "data_insights":[item["text"] for item in published_insights],
            "data_insight_evidence":published_insights,
            "data_insight_meta":{"status":"validated","families":["cartera","suscripciones","movilidad"],"period":period,"mobility_start":m["period_start"],"mobility_end":m["period_end"],
                                 "sha256":{k:families[k]["sha256"] for k in ("cartera","suscripciones","movilidad")},
                                 "anomaly_checks":analytic["anomaly_checks"],
                                 "publication_dates":{k:official[k]["event_date"] for k in ("cartera","suscripciones","movilidad")},
                                 "validated_at":validation["validated_at"],
                                 "validated_insight_count":len(analytic["insights"]),"published_sample_count":len(published_insights),
                                 "business_review":"sustained_contraction_and_mix_watch_without_causal_attribution",
                                 "business_metrics":business},
            "source_alternatives":[{**official[k],"workbook_url":families[k]["source_url"]} for k in ("cartera","suscripciones","movilidad")],
            "key_facts":[f"Cartera {period}: {benef} beneficiarios",f"Movilidad {m['period_start']} a {period}: {net}"],
        }
    except (KeyError,TypeError,ValueError,IndexError):
        return None
