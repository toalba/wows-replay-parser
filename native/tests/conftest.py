import pytest


@pytest.fixture
def native():
    import wows_native

    return wows_native
