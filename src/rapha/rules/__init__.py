"""The rules engine. Pure: state in, observations out.

No I/O, no clock reads, no database — every function takes what it needs as an
argument, including `today`. That is what makes the framework rules testable, and
it is why their output can be trusted.
"""
