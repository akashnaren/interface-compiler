"""Checks that run on a compiled document before a probe outcome is trusted.

The frozen ``x.page``, ``state_from``, ``entities_from``, ``precheck``,
``registry``, and ``blocked`` fields stay open objects. Checker code must not
require them to match the pydantic models.

This package init stays empty on purpose. ``contract.validate`` imports
``checker.verified`` while models are still loading, so importing a checker
module that imports the contract from here would cycle.
"""
