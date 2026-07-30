# Changelog

All notable changes to agentwisper are documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses [Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-07-31

### Changed
- Package restructured into the `agentwisper` namespace. Import paths changed from top-level (`broker`, `cli`, `common`, `persistence`, `mcp_server`) to namespaced (`agentwisper.broker`, etc.). Breaking for any code importing the package directly.
- Published to PyPI. Install with `pip install agentwisper`.

### Added
- Complete project metadata (license, classifiers, URLs).
- `agentwisper.__version__`.
- GitHub Actions workflow publishing to PyPI via OIDC trusted publisher, with a TestPyPI dry-run stage.

## [0.4.0] - 2026-07-28

- agentwisper-broker register/reconnect responses now include a `peers` snapshot of active agents.
