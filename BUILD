package(default_visibility = ["//visibility:public"])

load("@subpar//:subpar.bzl", "par_binary")

py_library(
    name = 'shared',
    srcs = glob(['Shared/**']),
)

py_library(
    name = 'simulator',
    srcs = glob(['SimulatorControl/**']),
    deps = [
        ':shared',
    ],
)

par_binary(
    name = 'ios_test_runner',
    srcs = glob(
        ['TestRunner/**'],
        exclude = ['TestRunner/TestProject/**']
    ),
    main = 'TestRunner/ios_test_runner.py',
    deps = [
        ':shared',
        ':simulator',
    ],
    data = glob(['TestRunner/TestProject/**']),
)
