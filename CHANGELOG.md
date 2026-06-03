# Changelog

All notable changes to hothog are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Initial public release, extracted and generalized from a real `django.setup()` optimization effort.
- Framework-agnostic entry: point at any `"module:callable"` (default `django:setup`) via `--entry`.
- Configurable `--first-party` packages and `--test-only` libraries (was hard-wired before).
- `hothog` console script + `python -m hothog`.
- Pure-core unit tests (importtime, dominators, deferability) and a synthetic end-to-end test
  covering the live import hook, entry resolution, and the full join — no Django/SDKs required.
