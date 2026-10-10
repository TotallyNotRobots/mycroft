FROM mcr.microsoft.com/devcontainers/python:3.13@sha256:5ea7e72d3c1beb6aefdfea8001483345c39af4898e22f2c543deb6a00802ede4

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
