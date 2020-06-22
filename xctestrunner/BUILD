package(default_visibility = ["//visibility:public"])

load("@subpar//:subpar.bzl", "par_binary")

py_library(
    name = "shared",
    srcs = glob(["shared/*.py"]),
)

py_library(
    name = "simulator",
    srcs = glob(["simulator_control/*.py"]),
    deps = [
        ":shared",
    ],
)

par_binary(
    name = "ios_test_runner",
    srcs = glob(
        ["test_runner/*.py"],
        exclude = ["test_runner/TestProject/**"],
    ),
    compiler_args = [
        "--interpreter",
        "/usr/bin/python2.7",
    ],
    data = glob(["test_runner/TestProject/**"]),
    main = "test_runner/ios_test_runner.py",
    python_version = "PY2",
    deps = [
        ":shared",
        ":simulator",
    ],
)
