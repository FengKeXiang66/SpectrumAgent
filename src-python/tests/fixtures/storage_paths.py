"""Separate mutable application roots from original synthetic source trees."""


def runtime_path(source_fixture, requested):
    return source_fixture.parent / (source_fixture.name + '-runtime') / requested.relative_to(source_fixture)
