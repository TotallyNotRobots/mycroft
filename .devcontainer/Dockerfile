FROM mcr.microsoft.com/devcontainers/python:3.11@sha256:2da3e966c6fde093c757c6ea372bfb5b4302c6ec7d9f5fb60796cd211aaacc67

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
