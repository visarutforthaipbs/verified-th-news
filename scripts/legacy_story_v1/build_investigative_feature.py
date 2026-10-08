#!/usr/bin/env python3
"""Rebuild the audited 11-year feature in HTML and Markdown.

The delivered CSV is the numerical source of truth. Original pre-audit
outputs/builders are preserved in data/reports/archive/.
"""
from _audited_features import build_feature


def main():
    for path in build_feature(1):
        print(f"Updated: {path}")


if __name__ == "__main__":
    main()
