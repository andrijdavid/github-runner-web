FROM python:3.11-slim-bookworm

ARG RUNNER_VERSION=2.335.1
ARG TARGETARCH

ENV PYTHONUNBUFFERED=1
ENV RUNNER_TEMPLATE_DIR=/opt/runner
ENV DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    jq \
    libicu72 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Install the GitHub Actions runner binary into a read-only template directory.
# At runtime we copy it into /data/runner so configuration and _work persist.
RUN mkdir -p "${RUNNER_TEMPLATE_DIR}" \
    && cd "${RUNNER_TEMPLATE_DIR}" \
    && if [ "$TARGETARCH" = "arm64" ]; then RUNNER_ARCH="linux-arm64"; else RUNNER_ARCH="linux-x64"; fi \
    && curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz" \
    && tar xzf runner.tar.gz \
    && rm runner.tar.gz \
    && ./bin/installdependencies.sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chmod +x /app/entrypoint.sh

# Run as a non-root user. Umbrel mounts app data as 1000:1000.
RUN groupadd -g 1000 runner && useradd -u 1000 -g runner -m runner \
    && mkdir -p /data \
    && chown -R runner:runner /app /data
USER runner:runner

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
