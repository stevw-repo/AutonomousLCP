FROM scratch

ARG SOURCE_DATE_EPOCH

COPY --chmod=0555 _generated/rootfs/ /
COPY --chmod=0444 rootfs/ /

LABEL org.opencontainers.image.created="1980-01-01T00:00:00Z"
LABEL org.opencontainers.image.description="Synthetic AskLegal image-admission fixture"
LABEL org.opencontainers.image.licenses="Apache-2.0 AND GPL-2.0-only"
LABEL org.opencontainers.image.revision="synthetic"
LABEL org.opencontainers.image.source="local://asklegal-image-admission-spike"
LABEL org.opencontainers.image.title="asklegal-image-admission-fixture"
LABEL org.opencontainers.image.version="1.0.0"

USER 10001:10001
WORKDIR /app
ENTRYPOINT ["/bin/busybox", "sh", "-c", "printf 'asklegal-image-admission-fixture\\n'"]
