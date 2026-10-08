#!/usr/bin/env python3
"""Rebuild the audited migrant feature without reclassifying the CSV.

Unknown/other frames remain separate; the population and partial-year
limitations are visible in both output formats.
"""
from _audited_features import build_feature


def generate_migrant_report():
    for path in build_feature(2):
        print(f"Updated: {path}")


if __name__ == "__main__":
    generate_migrant_report()
