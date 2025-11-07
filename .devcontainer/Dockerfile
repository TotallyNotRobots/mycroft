FROM mcr.microsoft.com/devcontainers/python:3.11@sha256:c1fd7d81fee8be5f9f441bdcaf9d61758d8f5bcdb59397092984fcc62c3ad2b0

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
