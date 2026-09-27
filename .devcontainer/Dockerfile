FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dtctl for running DQL queries from the terminal.
# https://github.com/dynatrace-oss/dtctl
RUN curl -fsSL https://raw.githubusercontent.com/dynatrace-oss/dtctl/main/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# dtctl stores tokens in the OS keyring by default, which doesn't exist in
# Docker. File mode writes credentials to ~/.config/dtctl instead.
ENV DTCTL_TOKEN_STORAGE=file

WORKDIR /workspace
