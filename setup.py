#!/usr/bin/env python3
"""Thin setuptools shim for the ddpa_layout package (a YOLOv5 fork).

All packaging metadata lives in ``pyproject.toml`` (PEP 621) so there is a SINGLE
authoritative source; duplicating it here would risk the two disagreeing and is exactly
the kind of change that can quietly break the fork's build. The project version is the
single source of truth in ``ddp_layout/version.py`` -- ``pyproject.toml`` reads it via
``[tool.setuptools.dynamic]``. This file exists only so ``python setup.py ...`` and older
tooling keep working; the real build backend is still ``setuptools.build_meta``.
"""
from setuptools import setup

setup()
