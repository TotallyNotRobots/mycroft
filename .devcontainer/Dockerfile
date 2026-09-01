FROM mcr.microsoft.com/devcontainers/python:3.14@sha256:97152d71a6e42cc2f4f39d68fe72a94fc10baeb203700296dd3b2db4cfaaa686

RUN \
    pipx uninstall pydocstyle \
    && pipx uninstall pycodestyle \
    && pipx uninstall mypy \
    && pipx uninstall pylint \
    && pipx uninstall pytest \
    && pipx uninstall flake8 \
    && pipx uninstall black

ENV SHELL /bin/bash
