from radar_salud.models import Signal
from radar_salud.translation import translate_signal_to_spanish, is_publishable_language


def _signal():
    return Signal(
        title="Hospital deals accelerate", source_name="Reuters", source_type="press_high_trust",
        source_url="https://example.com", category="Radar Mundo", subcategory="Radar Mundo",
        system_domain="GLOBAL_HEALTH", what_happened="Hospital deals accelerate in the US.",
        why_it_matters="This may anticipate consolidation trends.", original_language="en",
        display_language="es", translation_status="pending"
    )


def test_english_signal_not_publishable_until_translated():
    s=_signal()
    assert not is_publishable_language(s)


def test_translation_preserves_original_and_publishes_spanish():
    s=_signal()
    out=translate_signal_to_spanish(s, lambda text, _src, _dst: "ES: " + text)
    assert out.title.startswith("ES: ")
    assert out.original_title == "Hospital deals accelerate"
    assert out.translation_status == "translated"
    assert is_publishable_language(out)
