FROM mcr.microsoft.com/devcontainers/python:3.13@sha256:5bbf05ac5b550e812a3f7fb3c35c5e99131567f24fdb3e2d29525e5e1c6972a2

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
