"""Explicit direct local test client, independent of env and cached openers."""
import urllib.request


def urlopen(request,timeout=5):
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=timeout)
