"""Permite `python -m pingunews` (equivale a `python -m pingunews.cli`)."""
import sys

from pingunews.cli import main

sys.exit(main())
