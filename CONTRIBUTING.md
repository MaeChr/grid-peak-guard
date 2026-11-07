# Contributing / Mitmachen

Thanks for helping! Issues and pull requests in English or German are welcome.
Danke fürs Mithelfen! Issues und Pull Requests auf Deutsch oder Englisch sind willkommen.

## Development setup

```bash
python3.13 -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt ruff
pytest
ruff check custom_components tests && ruff format --check custom_components tests
```

hassfest runs in CI (`.github/workflows/validate.yml`).

Every change needs: tests, clean ruff, passing hassfest and a `CHANGELOG.md` entry.

## Add a device model (no code)

Create `custom_components/grid_peak_guard/profiles/<category>/<model>.json`:

```json
{
  "id": "my_model",
  "name": "Vendor Model (what is controlled)",
  "category": "wallbox",
  "defaults": {"priority": 20, "reduce_value": "6"},
  "suggestions": {"control_entity": "vendor.*current", "power_entity": "vendor.*power"},
  "notes": "Anything users must check."
}
```

- `defaults` and `suggestions` may only use fields of that category (see `devices/<category>.py`).
- `suggestions` are case-insensitive regular expressions matched against entity IDs. Never put real entity IDs from your own installation into a profile.
- The test `tests/test_profiles_translations.py` validates every profile.

## Add a device category (code)

1. Add `devices/<category>.py` with a `BaseDevice` subclass decorated with `@register`, its `fields`, `default_priority` and, if needed, `can_reduce`, `should_release`, `update`, `expected_extra_kw`.
2. Import it in `devices/__init__.py` and add it to `CATEGORIES`.
3. Add `profiles/<category>/generic.json`.
4. Add labels for new fields and the category to `strings.json` and every `translations/*.json`.
5. Add tests, including the protection behaviour.

Device control is safety-relevant: never weaken protection times, the restore at window end or simulation mode, and describe risks in the pull request.

## Add a UI language

Copy `translations/en.json` to `translations/<lang>.json` and translate the values. Keys must stay identical (checked by the tests).
