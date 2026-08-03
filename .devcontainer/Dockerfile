FROM mcr.microsoft.com/devcontainers/python:3.11@sha256:374280c968dfe119bedb3bcfdba3da43da457888f6ea3c527f6f33a7ac7589e9

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
