FROM mcr.microsoft.com/devcontainers/python:3.11@sha256:d72636002e857ef8786cc7a19aee6e2806ec8c6f52ac45c98a35c343eb3c290b

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
