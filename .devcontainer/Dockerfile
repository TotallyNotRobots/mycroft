FROM mcr.microsoft.com/devcontainers/python:3.13@sha256:c6586000d784e1082807570db10e6f392f54f9706ee6baaf87d558f301615c7a

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
