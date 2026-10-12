# syntax=docker/dockerfile:1
FROM node:24-slim AS ui
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY vite.config.js ./
COPY web ./web
COPY scripts/build-ui-policy.mjs ./scripts/build-ui-policy.mjs
RUN npm run build

FROM python:3.12-slim-trixie
LABEL org.opencontainers.image.title="Popcorn SR" \
      org.opencontainers.image.source="https://github.com/thekozugroup/Popcorn-SR" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 -m popcorn \
    && mkdir /state /library /output /scratch && chown popcorn:popcorn /state /library /output /scratch
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY LICENSE THIRD-PARTY-NOTICES.md ./
COPY licenses ./licenses
COPY popcorn_sr ./popcorn_sr
COPY --from=ui /build/popcorn_sr/static ./popcorn_sr/static
RUN pip install uv==0.8.22 && uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python
ENV PATH="/app/.venv/bin:$PATH"
USER 1000:1000
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3)"
ENTRYPOINT ["/usr/bin/tini", "--", "popcorn-sr"]
CMD ["serve"]
