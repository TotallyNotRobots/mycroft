FROM mcr.microsoft.com/devcontainers/python:3.12@sha256:a00123df1ec4af04b4013fda8c27438b73b1817a24f6bcd3d61e2f6aa0800302

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
