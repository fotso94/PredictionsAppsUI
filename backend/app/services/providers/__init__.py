"""
Provider integrations for match data (fixtures, live scores, standings, results)
and third-party forecasts.

Active providers are selected through settings (DATA_PROVIDER, DATA_PROVIDER_FALLBACKS,
PREDICTION_PROVIDER). Every provider normalises its payloads into the DTOs defined in
`base.py`; nothing provider-specific leaks past this package.
"""
