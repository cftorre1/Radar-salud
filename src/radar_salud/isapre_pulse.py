"""Factual pulse from three reconciled official workbook families; fail closed."""
from datetime import date, timedelta
from urllib.parse import urlparse
import re

from .isapre_insights import derive


def _count(value):
    if not isinstance(value,int) or isinstance(value,bool) or value<0:
        raise ValueError("Invalid count")
    return value


def build_pulse(validation):
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
        period_end=(date(end.year+1,1,1) if end.month==12 else date(end.year,end.month+1,1))-timedelta(days=1)
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
        label=lambda v:f"{v:,}".replace(",",".")
        start_label=start.strftime("%m-%Y");end_label=end.strftime("%m-%Y")
        return {
            "title":f"Pulso Isapre · datos a {period}","source_name":"Superintendencia de Salud",
            "source_type":"official","source_url":car["source_url"],"event_date":period_end.isoformat(),"data_period":period,
            "signal_types":["Datos"],"scopes":["Isapres"],"ingestion_mode":"BACKFILL",
            "category":"Datos sectoriales","event_type":"DATA_PULSE","distribution":"archive",
            "radar_score":72,"confidence_score":100,
            "what_happened":f"Las series oficiales del sistema Isapre registran a {period} una cartera de {label(benef)} beneficiarios ({label(cot)} cotizantes y {label(cargas)} cargas).",
            "why_it_matters":"Permite leer juntos el tamaño de la cartera, las suscripciones y desahucios voluntarios mensuales, y la movilidad entre dos cortes anuales. Son medidas de períodos distintos; no prueban causas ni una tendencia por sí solas.",
            "key_points":[f"En {period} se registraron {label(contracts)} contratos suscritos y {label(voluntary)} desahucios voluntarios; estos últimos no representan todas las terminaciones.",
                f"Entre los cortes {start_label} y {end_label} se registraron {label(exits)} salidas y {label(entries)} entradas por movilidad; diferencia entradas menos salidas: {label(net)}."],
            # FREE shows one sourced sample. The complete set remains in the
            # internal evidence report until PREMIUM access is approved.
            "data_insights":[analytic["insights"][0]["text"]],
            "data_insight_evidence":[analytic["insights"][0]],
            "data_insight_meta":{"status":"validated","families":["cartera","suscripciones","movilidad"],"period":period,"mobility_start":m["period_start"],"mobility_end":m["period_end"],
                                 "sha256":{k:families[k]["sha256"] for k in ("cartera","suscripciones","movilidad")},
                                 "anomaly_checks":analytic["anomaly_checks"],
                                 "validated_insight_count":len(analytic["insights"]),"published_sample_count":1},
            "source_alternatives":[{"title":k,"source_name":"Superintendencia de Salud","url":families[k]["source_url"]} for k in ("suscripciones","movilidad")],
            "key_facts":[f"Cartera {period}: {benef} beneficiarios",f"Movilidad {m['period_start']} a {period}: {net}"],
        }
    except (KeyError,TypeError,ValueError,IndexError):
        return None
