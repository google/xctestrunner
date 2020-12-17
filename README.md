# XCTestRunner
A tool for running prebuilt iOS tests on iOS real device and simulator.

## Features
- It supports XCTest (Xcode Unit Test), XCUITest (Xcode UI Test).
- It supports iOS 7+ iOS real device, iOS simulator.
- It supports launch options configuration: test methods to run, additional
environment variables, additional arguments.
- It supports Xcode 8+.

## Prerequisites
- Install Xcode (Xcode 8+). XCUITest support requires Xcode 8+.
- [Install bazel](https://docs.bazel.build/install.html) (optional).
- py module [biplist](https://github.com/wooster/biplist).

## Installation
You can download the ios_test_runner.par binary in [release](https://github.com/google/xctestrunner/releases)

or build the ios_test_runner.par binary by bazel:
```
$ git clone https://github.com/google/xctestrunner.git
$ cd xctestrunner
$ bazel build :ios_test_runner.par
$ ls bazel-bin/ios_test_runner.par
```

## Usage
- Build your app under test and test bundle. You can use Xcode.app,
`xcodebuild` command line tool or [bazel](https://github.com/bazelbuild/bazel).
- Run the ios_test_runner.par binary.

In overview, there are two sub-commands in the runner binary.
- `test`: Run test directly on connecting iOS real device or existing iOS
simulator.
- `simulator_test`: Run test on a new created simulator, which will be deleted
after test finishes.

See more details by running `ios_test_runner.par -h` in terminal.

## Notes

Disclaimer: This is not an official Google product.

XCTestRunner uses Apple native tool `xcodebuild`, `simctl` to control iOS
Simulator and launch tests on iOS devices.

For testing, XCTestRunner injects app under test and test bundle file into a
dummy project. Then the dummy project can be used `xcodebuild test` to run
XCTest (not for XCUITest), or `xcodebuild build-for-testing` to generate
xctestrun file for further testing.

For iOS 7 real device testing, the latest supported Xcode version is 7.2.1.
For iOS 7 simulator testing, latest supported Xcode version is 7.2.1 and latest
supported MacOS version is Yosemite (10.10.x).
