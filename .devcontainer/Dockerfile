FROM mcr.microsoft.com/devcontainers/python:3.13@sha256:e3eb101f2fc907ea2aeec4a648a947c953d842e31ccd765a4a5fe528515b16b2

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
