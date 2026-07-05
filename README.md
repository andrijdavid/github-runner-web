# GitHub Runner Web

A browser-managed wrapper around the official GitHub Actions self-hosted runner.
Run it anywhere Docker runs, including Umbrel, a VPS, or your own server.

## Features

- Web UI to attach the runner to a repository, organisation, or enterprise.
- Set runner name, labels/tags, runner group, and ephemeral mode.
- Live log streaming of runner output.
- Persists runner registration and state across container restarts.

## Image

`ghcr.io/andrijdavid/github-runner-web`

Supports `linux/amd64` and `linux/arm64`.

## Usage

```sh
docker run -d \
  --name github-runner \
  -p 8080:8080 \
  -v $(pwd)/runner-data:/data \
  ghcr.io/andrijdavid/github-runner-web:latest
```

Open `http://localhost:8080`, paste your GitHub runner registration token, and
attach the runner.

## Umbrel

This image is also packaged as an Umbrel app. See the app package in
`andrijdavid/umbrel-apps`.

## License

AGPL-3.0
