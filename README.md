# Umbrel GitHub Actions Runner

A small wrapper around the official GitHub Actions self-hosted runner that adds a browser-based setup UI and live log viewer. Packaged for [Umbrel](https://umbrel.com).

## Features

- Web UI to attach the runner to a repository, organisation, or enterprise.
- Set runner name, labels/tags, runner group, and ephemeral mode.
- Live log streaming of runner output.
- Persists runner registration and state across container restarts.

## Image

`andrijdavid/umbrel-github-runner`

Supports `linux/amd64` and `linux/arm64`.

## License

AGPL-3.0
