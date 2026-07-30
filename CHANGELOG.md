# Changelog

All notable changes to agentsquad are documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses [Semantic Versioning](https://semver.org/).

## [0.5.0] - UNRELEASED

### Changed
- Package restructured into the `agentsquad` namespace. Import paths changed from top-level (`broker`, `cli`, `common`, `persistence`, `mcp_server`) to namespaced (`agentsquad.broker`, etc.). Breaking for any code importing the package directly.
- Published to PyPI. Install with `pip install agentsquad`.

### Added
- Complete project metadata (license, classifiers, URLs).
- `agentsquad.__version__`.
- GitHub Actions workflow publishing to PyPI via OIDC trusted publisher, with a TestPyPI dry-run stage.

## [0.4.0] - 2026-07-28

- agentsquad-broker register/reconnect responses now include a `peers` snapshot of active agents.
