FROM python:3.11-slim@sha256:65bd3d9f1d7fa268dd1909973ba7eb4bdf41f6dcf2cfbe76ba9528b170f3fd79
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
ARG INSTALL_DASHBOARD=0
RUN pip install --no-cache-dir uv==0.13.7 && uv sync --frozen --no-dev --no-install-project && if [ "$INSTALL_DASHBOARD" = "1" ]; then uv sync --frozen --no-dev --extra dashboard --no-install-project; fi
COPY app ./app
COPY dashboard ./dashboard
COPY datasets ./datasets
COPY scripts ./scripts
ENV PATH="/workspace/.venv/bin:$PATH"
RUN useradd --create-home lab && mkdir -p /workspace/.runtime && chown -R lab:lab /workspace
USER lab
CMD ["python", "-m", "scripts.start"]
