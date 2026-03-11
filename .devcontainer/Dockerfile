FROM mcr.microsoft.com/devcontainers/python:3.11@sha256:f46978552419eb3cbf3bcf662ba0dca1639b07307f64447a3fcbe46110710b27

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
