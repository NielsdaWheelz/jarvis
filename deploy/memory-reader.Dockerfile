FROM ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b AS uv

FROM pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b AS postgres

FROM postgres AS build
COPY --from=uv /uv /bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && rm -rf /var/lib/apt/lists/*
ENV UV_PYTHON_INSTALL_DIR=/opt/jarvis/.python
WORKDIR /opt/jarvis
COPY .python-version README.md pyproject.toml uv.lock ./
COPY src/ src/
RUN uv python install --no-bin && uv sync --frozen --no-dev --no-editable --no-python-downloads

FROM postgres
COPY --from=build /opt/jarvis/.python /opt/jarvis/.python
COPY --from=build /opt/jarvis/.venv /opt/jarvis/.venv
COPY uv.lock /opt/jarvis/uv.lock
COPY deploy/memory_snapshot.py deploy/memory_reader.py /opt/jarvis/deploy/
ENTRYPOINT ["/opt/jarvis/.venv/bin/python", "/opt/jarvis/deploy/memory_reader.py"]
