FROM mcr.microsoft.com/devcontainers/python:3.12@sha256:79a80515d78783e761af1db255e92767c4e887a2d56dbeb85e7753da8c12dc16

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
