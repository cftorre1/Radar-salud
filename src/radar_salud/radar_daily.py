from __future__ import annotations

from datetime import date
from typing import Iterable, List

from .models import Signal
from .multisource import rank_for_profile, RankedSignal
from .personalization import UserProfile
from .translation import is_publishable_language


def _icon(score: int) -> str:
    if score >= 90: return '🔴'
    if score >= 75: return '🟠'
    return '🟡'


def select_daily(signals: Iterable[Signal], profile: UserProfile, local_limit: int = 5, world_limit: int = 2) -> List[RankedSignal]:
    ranked = [rs for rs in rank_for_profile(signals, profile) if is_publishable_language(rs.signal)]
    local, world = [], []
    for rs in ranked:
        if rs.signal.category == 'Radar Mundo' or rs.signal.system_domain == 'GLOBAL_HEALTH':
            if len(world) < world_limit:
                world.append(rs)
        elif len(local) < local_limit:
            local.append(rs)
    return local + world


def build_whatsapp_daily(signals: Iterable[Signal], profile: UserProfile, digest_date: str | None = None) -> str:
    day = digest_date or date.today().isoformat()
    selected = select_daily(signals, profile)
    local = [x for x in selected if x.signal.category != 'Radar Mundo']
    world = [x for x in selected if x.signal.category == 'Radar Mundo']
    lines = [f'RADAR SALUD · {day}', f'{profile.label}', '', f'{len(local)} señales relevantes para ti', '']
    for i, rs in enumerate(local, 1):
        s=rs.signal
        lines += [f'{_icon(rs.personal_score)} {i}. {s.title}']
        if s.what_happened and s.what_happened != s.title: lines += [f'Qué pasó: {s.what_happened}']
        if s.why_it_matters: lines += [f'Por qué importa: {s.why_it_matters}']
        lines += [f'Fuente: {s.source_name} · Confianza {s.confidence_score}']
        if s.source_url: lines += [f'Más información: {s.source_url}']
        lines += ['']
    if world:
        lines += ['🌎 RADAR MUNDO', '']
        for rs in world:
            s=rs.signal
            lines += [f'• {s.title}']
            if s.what_happened and s.what_happened != s.title: lines += [f'  Qué pasó: {s.what_happened}']
            if s.why_it_matters: lines += [f'  Por qué mirar: {s.why_it_matters}']
            lines += [f'  Fuente: {s.source_name}']
            if s.source_url: lines += [f'  Más información: {s.source_url}']
            lines += ['']
    lines += ['Watch específicos pueden generar alertas aparte durante el día.']
    return '\n'.join(lines).rstrip()+'\n'
