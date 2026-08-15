# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ARG PYTHON_VERSION
ARG APP_UID=1000
ARG APP_GID=1000

RUN python -c 'import sys; minimum=(3, 11); actual=sys.version_info[:2]; requested=sys.argv[1]; raise SystemExit(f"ERROR: PYTHON_VERSION={requested!r} resolved to Python {sys.version.split()[0]}; this project requires Python >= 3.11" if actual < minimum else 0)' "${PYTHON_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --gid "${APP_GID}" simulator \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --home-dir /nonexistent simulator \
    && mkdir -p /output \
    && chown simulator:simulator /output

COPY --chown=simulator:simulator src/ ./src/

USER simulator

FROM base AS test

COPY --chown=simulator:simulator tests/ ./tests/
COPY --chown=simulator:simulator Dockerfile compose.yaml pyproject.toml ./

CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]

FROM base AS runtime

ENTRYPOINT ["python", "-m", "sr22_course_simulator.examples.spiral_descent"]
CMD ["--mode", "guided"]
