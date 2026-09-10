FROM mcr.microsoft.com/devcontainers/python:3.11@sha256:01f7fa973e78e9e106b347ebe9b4c85e46c7d67f839c21ba7ba4fd930a6518e1

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
