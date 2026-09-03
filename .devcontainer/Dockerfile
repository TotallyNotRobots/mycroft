FROM mcr.microsoft.com/devcontainers/python:3.12@sha256:7ae01dce85c08cc6b6ca411d7d7051eb100d2274ee2702120c11236692b6204f

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
