import json
import re
from pathlib import Path

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / "dwarf_mini"
ALL_TRANSLATION_FILES = ("strings.json", "translations/en.json", "translations/de.json", "translations/nl.json")


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _keys(d: dict, prefix: str = "") -> set[str]:
    keys = set()
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _keys(v, full)
        else:
            keys.add(full)
    return keys


def test_all_translation_files_are_valid_json():
    for name in ALL_TRANSLATION_FILES:
        _load(INTEGRATION_DIR / name)  # raises if invalid


def test_strings_and_en_translation_have_identical_keys():
    strings = _keys(_load(INTEGRATION_DIR / "strings.json"))
    en = _keys(_load(INTEGRATION_DIR / "translations" / "en.json"))
    assert strings == en


def test_de_and_nl_have_same_keys_as_strings():
    strings = _keys(_load(INTEGRATION_DIR / "strings.json"))
    for lang in ("de", "nl"):
        translated = _keys(_load(INTEGRATION_DIR / "translations" / f"{lang}.json"))
        assert translated == strings, f"{lang}.json key mismatch: {strings ^ translated}"


def test_exception_placeholders_match():
    """The {placeholder} tokens in capture_command_rejected must match across all languages.

    Catches drift such as a typo'd {Code} in one translation file while the
    others use {code} - a mismatch hassfest/HA's translation loader would not
    otherwise flag at collection time.
    """
    placeholder_sets = {}
    for name in ALL_TRANSLATION_FILES:
        data = _load(INTEGRATION_DIR / name)
        message = data["exceptions"]["capture_command_rejected"]["message"]
        placeholder_sets[name] = set(re.findall(r"\{[^}]*\}", message))

    reference_name = ALL_TRANSLATION_FILES[0]
    reference = placeholder_sets[reference_name]
    assert reference, f"{reference_name} has no placeholders in capture_command_rejected.message"
    for name, placeholders in placeholder_sets.items():
        assert placeholders == reference, (
            f"{name} placeholders {placeholders} != {reference_name} placeholders {reference}"
        )
