# syntax=docker/dockerfile:1
#
# One reproducible V1 application image, parameterised by application.
#
# Every input is pinned: the base image by digest, the interpreter by that image,
# the third-party wheels by the locked offline wheelhouse and their hashes, and
# the workspace distributions by the exact uv lock. The build has no network:
# `pip install --no-index` cannot reach an index, so an input that is not in the
# build context cannot silently be fetched.
#
# The image is not admitted by being built. It runs as a non-root numeric identity
# with no shell entrypoint, and its runtime hardening (read-only root filesystem,
# NoNewPrivileges, empty capability set) is applied by the systemd unit, not here.

ARG BASE_IMAGE
ARG RUNTIME_VARIANT=plain
FROM ${BASE_IMAGE} AS build

ARG APPLICATION
ARG SOURCE_DATE_EPOCH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}

WORKDIR /build
COPY wheelhouse /build/wheelhouse
COPY workspace /build/workspace

RUN python -m venv /opt/asklegal \
 && /opt/asklegal/bin/pip install --no-index --find-links=/build/wheelhouse/wheels \
      --require-hashes -r /build/wheelhouse/${APPLICATION}.txt \
 && /opt/asklegal/bin/pip install --no-index --no-deps /build/workspace/*.whl \
 && ln -s "/opt/asklegal/bin/${APPLICATION}" /opt/asklegal/bin/asklegal-service \
 && find /opt/asklegal -name '__pycache__' -type d -prune -exec rm -rf {} + \
 && find /opt/asklegal -newermt "@${SOURCE_DATE_EPOCH}" -exec touch --no-dereference \
      --date="@${SOURCE_DATE_EPOCH}" {} +

FROM ${BASE_IMAGE} AS runtime-base

ARG APPLICATION
ARG RUNTIME_UID
ARG SOURCE_DATE_EPOCH

# The bundled ODBC driver links against Kerberos and libltdl, which the slim base
# image does not carry. These .deb files are pinned by hash in
# application_system_packages.json and installed offline; dpkg cannot reach a
# mirror, so an unpinned package cannot slip in.
COPY debs /tmp/debs
RUN dpkg --install /tmp/debs/*.deb \
 && rm -rf /tmp/debs /var/lib/apt/lists/*

COPY --from=build /opt/asklegal /opt/asklegal

ENV PATH="/opt/asklegal/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

FROM runtime-base AS runtime-browser

# Only the acquisition image selects this stage. Both directories are verified
# byte-for-byte before Docker is invoked; dpkg has no network route here.
COPY browser-runtime /opt/asklegal/ms-playwright
COPY browser-debs /tmp/browser-debs
RUN dpkg --install /tmp/browser-debs/*.deb \
 && rm -rf /tmp/browser-debs /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/asklegal/ms-playwright

FROM runtime-base AS runtime-plain

FROM runtime-${RUNTIME_VARIANT} AS runtime-selected

ARG RUNTIME_UID

USER ${RUNTIME_UID}:${RUNTIME_UID}
ENTRYPOINT ["/opt/asklegal/bin/asklegal-service", "--serve"]
