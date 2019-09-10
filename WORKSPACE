# For packaging python scripts.
load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

git_repository(
    name = "rules_python",
    commit = "54d1cb35cd54318d59bf38e52df3e628c07d4bbc",
    remote = "https://github.com/bazelbuild/rules_python.git",
    shallow_since = "1567788415 -0400",
)

load("@rules_python//python:repositories.bzl", "py_repositories")

py_repositories()

git_repository(
    name = "subpar",
    commit = "35bb9f0092f71ea56b742a520602da9b3638a24f",
    remote = "https://github.com/google/subpar",
    shallow_since = "1557863961 -0400",
)
