FROM mcr.microsoft.com/devcontainers/python:3.11@sha256:6cfee5f60ec1b79a35a33bbd2b2b433b0e812b49ddc7a40aee8cdea8cd02d12d

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
