"""Toy entry point. Calling run() pulls the api package, mirroring a framework's boot()."""


def run():
    from sample_app import api  # noqa: F401  (importing the package is the whole point)
