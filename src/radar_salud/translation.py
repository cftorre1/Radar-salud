from __future__ import annotations

from dataclasses import replace
from typing import Callable

from .models import Signal


Translator = Callable[[str, str, str], str]


def needs_spanish_translation(signal: Signal) -> bool:
    return (signal.original_language or 'es').lower() != 'es'


def translate_signal_to_spanish(signal: Signal, translator: Translator) -> Signal:
    """Return a user-facing Spanish copy while preserving original text.

    translator(text, source_lang, target_lang) is injected so V0 can use any
    approved LLM/provider later without coupling the domain model to one vendor.
    """
    source_lang = signal.original_language or 'en'
    if source_lang.lower() == 'es':
        signal.display_language = 'es'
        signal.translation_status = 'not_required'
        return signal

    original_title = signal.original_title or signal.title
    original_what = signal.original_what_happened or signal.what_happened
    original_why = signal.original_why_it_matters or signal.why_it_matters

    return replace(
        signal,
        original_title=original_title,
        original_what_happened=original_what,
        original_why_it_matters=original_why,
        title=translator(original_title, source_lang, 'es'),
        what_happened=translator(original_what, source_lang, 'es'),
        why_it_matters=translator(original_why, source_lang, 'es'),
        display_language='es',
        translation_status='translated',
    )


def is_publishable_language(signal: Signal) -> bool:
    """User-facing Radar is Spanish-only in V0."""
    return (signal.display_language or 'es').lower() == 'es' and signal.translation_status != 'pending'
