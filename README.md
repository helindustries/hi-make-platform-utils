# Hel Industries Make Platform Utilities

This repository is a collection of tools and Makefile includable files for dealing with platform-specific requirements
in a light-weight (as in not as heavy as w64devkit) way to enable porting Makefile-based and developing them using
the builtin POSIX-like environments like MinGW, commonly shipped with IDEs. The goal was not to replicate tools directly
to allow running existing Makefiles, but rather to provide an equivalent set of tools using (as yet rough and ready)
Python scripts.

## Requirements

- Make somewhere in path, using for example Cygwin, w64devkit or MinGW (i. e. the one shipped with Jetbrains CLion)
- Any Python 3.8 or later, no extra modules required, but must match your environment. So no using the Cygwin Python
  with MinGW or w64devkit Make.

## Usage

- Clone this repository somewhere, ideally as a submodule of your project
- Add the following line to your Makefile:
  ```make
  include <path-to-this-repo>/PlatformUtils.mk
  ```
- Use the defined commands in your Makefile, i. e.
  ```make
  $(call lower,$(MYVAR))
  ```
  or
  ```make
  $(call latest,"Path/To/Your/Toolchain/*/Processor")
  ```
- You can also call make_platform_utils.py directly to perform more complex operations. Use
  ```bash
  python3 <path-to-this-repo>/make_platform_utils.py --help
  ```
  to get a list of all available commands. The script is designed to be run from the command line, but when including
  PlatformUtils.mk, it is available as $(MAKE_PLATFORM_UTILS). The command arguments are chained and depend on the
  output similar to how pipes work on POSIX systems and output can be redirected to file and/or stdout with control
  over stdout and stderr from any sub-commands as it is meant as a replacement for pipes and redirects that do not
  work the same way on Windows. Care must be taken though, the script is not optimized for memory usage or realtime
  feedback, it will dump the full content of a command to memory before printing it or processing it for the next
  command for now for simplicity reasons.