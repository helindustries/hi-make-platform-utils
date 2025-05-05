#  Copyright 2025 $author, All rights reserved.
#
# This file attempts to replace common Unix tools for the specific purpose of substituting them on all
# platforms and removing the reliance on Cygwin or MSYS2 installations as much as possible.
#
# The implementation is not using generators, because it makes the code simpler and more explicit for
# now and the negative impact on memory is currently not worth the effort.
import os
import re
import sys
import glob
import shutil
import subprocess
from datetime import datetime
from typing import Optional, Any, ClassVar, Union, TextIO, List, Dict, Callable, Tuple

# <editor-fold desc="Python 3.9- Compatibility">
def removeprefix(string: str, prefix: str) -> str:
    """Remove the prefix from a string"""
    if string.startswith(prefix):
        return string[len(prefix):]
    return string
def removesuffix(string: str, suffix: str) -> str:
    """Remove the suffix from a string"""
    if string.endswith(suffix):
        return string[:-len(suffix)]
    return string
# </editor-fold>
class CommandResults:
    Ok: ClassVar[int] = 0
    UndefinedError: ClassVar[int] = 1
    RegexError: ClassVar[int] = 2
    IOError: ClassVar[int] = 3
    InvalidLine: ClassVar[int] = 4
    InvalidEnvValue: ClassVar[int] = 5
    MissingParameter: ClassVar[int] = 6
    UnknownArgument: ClassVar[int] = 7
    NoCommands: ClassVar[int] = 8
    CommandError: ClassVar[int] = 9
    CommandNotFoundError: ClassVar[int] = 10
    CommandExecFailedError: ClassVar[int] = 11
    CommandOSError: ClassVar[int] = 12
    InvalidOutputMode: ClassVar[int] = 13
    InvalidSortFlag: ClassVar[int] = 14
    InvalidSortColumn: ClassVar[int] = 15
    InvalidSortValue: ClassVar[int] = 16
    InvalidSumFlag: ClassVar[int] = 17
    InvalidSumValue: ClassVar[int] = 18
    InvalidFilterFlag: ClassVar[int] = 19
    Not: ClassVar[int] = 20
    @classmethod
    def check(cls, result: int) -> bool:
        return result >= cls.Ok and result <= cls.Not

class ParameterCountError(Exception):
    def __init__(self, message: str):
        self.message = message
    def __str__(self):
        return self.message

class CommandOutputMode:
    Process: ClassVar[str] = "process"
    Print: ClassVar[str] = "print"
    Ignore: ClassVar[str] = "ignore"
    Write: ClassVar[str] = "write"
    @classmethod
    def check(cls, mode: str) -> bool:
        return mode in [cls.Process, cls.Print, cls.Ignore, cls.Write]

class CommandProcessor:
    class Command:
        def __init__(self, arg_long: str, arg_short: str = None, param_names = None, param_count: int = -1, param_until: str = None, param_convert: Callable = None, desc: str = None):
            self.desc = desc
            self.arg_long = arg_long
            self.arg_short = arg_short
            self.param_names = param_names if param_names else [f"ARG{i}" for i in range(param_count)]
            # Use param_count if explicitly specified, use -1 if param_until is still set, resulting in both the option to limit the parameter count
            # and provide a delimiter. If neither is set explicitly, default to the length of param_names if given, or 0 as a default.
            self.param_count = param_count if param_count >= 0 else -1 if param_until else len(param_names) if param_names else 0
            self.param_until = param_until
            self.param_convert = param_convert
        def __call__(self, func):
            self.func = func
            func.command_attrs = self
            return func

    win_path_re: ClassVar[re.Pattern] = re.compile(r"^(?P<drive>[a-zA-Z]+):[\\/](?P<path>.*)$")
    cygwin_path_re: ClassVar[re.Pattern] = re.compile(r"^/cygdrive/(?P<drive>[a-zA-Z]+)/(?P<path>.*)$")
    msys2_path_re: ClassVar[re.Pattern] = re.compile(r"^/(?P<drive>[a-zA-Z]+)/(?P<path>.*)$")

    args: List[str]
    working_dir: str
    env: Dict[str, str]
    current_output: str
    stdout_mode: str
    stdout_path: Optional[str]
    stderr_mode: str
    stderr_path: Optional[str]
    stop_on_error: bool

    def __init__(self, args: List[str], working_dir: str = None):
        self.name = os.path.basename(sys.argv[0])
        self.args = args[1:]
        self.working_dir = working_dir if working_dir else os.getcwd()
        self.env = os.environ.copy()
        self.stdout_mode = CommandOutputMode.Process
        self.stdout_path = None
        self.stderr_mode = CommandOutputMode.Print
        self.stderr_path = None
        self.stop_on_error = True
        self.current_output = ""

    def get_pipe_target(self, mode: str, path: str, pipe, sysout) -> Union[int, TextIO]:
        """Get the pipe target for the command"""
        if mode == CommandOutputMode.Process:
            return pipe
        elif mode == CommandOutputMode.Write:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            return open(path, 'w')
        elif mode == CommandOutputMode.Ignore:
            return subprocess.DEVNULL
        else:
            return sysout

    def exec_cmd(self, command: str, args: Tuple[Any,...] = None) -> Tuple[int, str]:
        """Execute a command and return the result"""
        output: str = ""
        stdout = self.get_pipe_target(self.stdout_mode, self.stdout_path, subprocess.PIPE, sys.stdout)
        stderr = self.get_pipe_target(self.stderr_mode, self.stderr_path, subprocess.STDOUT, sys.stderr)
        command_args = [command]
        command_args.extend(args)
        result = CommandResults.UndefinedError
        try:
            process = subprocess.Popen(command_args,
                                       env=self.env,
                                       cwd=self.working_dir,
                                       stdout=stdout,
                                       stderr=stderr,
                                       text=True)
            out, err = process.communicate()
            if self.stdout_mode == CommandOutputMode.Process or self.stderr_mode == CommandOutputMode.Process:
                output = removesuffix(out, "\n") if out else ""

            if process.returncode == 0:
                result = CommandResults.Ok
            else:
                result = CommandResults.CommandError
                message = f"Error executing command: {command} {args} returned {process.returncode}"
                if self.stderr_mode == CommandOutputMode.Print:
                    print(message)
                elif self.stderr_mode == CommandOutputMode.Process:
                    output += f"\n{message}"
                elif self.stderr_mode == CommandOutputMode.Write:
                    stderr.write(f"\n{message}")
        except FileNotFoundError as e:
            print(f"Command not found: {command} {args}")
            result = CommandResults.CommandNotFoundError
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {command} {args} with error: {e}")
            result = CommandResults.CommandExecFailedError
        except OSError as e:
            print(f"OS error: {e}")
            result = CommandResults.CommandOSError
        except Exception as e:
            print(f"Unknown error: {e}")
            result = CommandResults.CommandError
        finally:
            if self.stdout_mode == CommandOutputMode.Write:
                try:
                    stdout.close()
                except:
                    pass
            if self.stderr_mode == CommandOutputMode.Write:
                try:
                    stderr.close()
                except:
                    pass

        return result, output

    # <editor-fold desc="Utilities">
    @Command("--env", desc="Set an environment variable", param_names=["KEY=VALUE"])
    def set_env(self, env: str) -> int:
        """Set an environment variable"""
        if "=" in env:
            key, value = env.split("=", 1)
            self.env[key] = value
            return CommandResults.Ok
        else:
            return CommandResults.InvalidEnvValue

    @Command("--stdout", desc="Set the stdout mode", param_names=["MODE|PATH"])
    def set_stdout(self, mode: str) -> int:
        """Set the stdout mode"""
        if mode in [CommandOutputMode.Process, CommandOutputMode.Print, CommandOutputMode.Ignore]:
            self.stdout_mode = mode
            self.stdout_path = None
        else:
            self.stdout_mode = CommandOutputMode.Write
            self.stdout_path = mode
        return CommandResults.Ok

    @Command("--stderr", desc="Set the stderr mode", param_names=["MODE|PATH"])
    def set_stderr(self, mode: str) -> int:
        """Set the stderr mode"""
        if mode in [CommandOutputMode.Process, CommandOutputMode.Print, CommandOutputMode.Ignore]:
            self.stderr_mode = mode
            self.stderr_path = None
        else:
            self.stderr_mode = CommandOutputMode.Write
            self.stderr_path = mode
        return CommandResults.Ok

    @Command("--stoponerror", desc="Set the exit mode", param_names=["MODE"])
    def set_exit(self, mode: str) -> int:
        """Set the exit mode"""
        mode = mode.strip().lower()
        if mode not in ["true", "false"]:
            print(f"Invalid exit mode: {mode}")
            return CommandResults.InvalidOutputMode
        self.stop_on_error = mode != "false"
        return CommandResults.Ok

    @Command("--help", "-h", desc="Show help")
    def print_help(self) -> int:
        """Show help for all commands"""
        print(f"Usage: {self.name} [COMMANDS]")
        print("Available commands:")
        for name, value in self.__class__.__dict__.items():
            if callable(value) and hasattr(value, 'command_attrs'):
                command = value.command_attrs
                if command.arg_short:
                    arg = f"{command.arg_long:>13}|{command.arg_short}"
                else:
                    arg = f"{command.arg_long:>13}   "

                params = " ".join(command.param_names)
                params = f" {params}" if len(command.param_names) > 0 else ""
                if command.param_until:
                    params += f" {command.param_until}"

                print(f"{arg}{params:<20}  {command.desc}")
        return CommandResults.Ok

    @Command("--platform-exec", desc="Get the platform executable helper")
    def platform_exec(self) -> int:
        """Get the platform executable helper"""
        if os.name == 'nt' or sys.platform == 'cygwin':
            self.current_output += ""
        elif sys.platform == 'darwin':
            self.current_output += "open"
        else:
            self.current_output += ""
        return CommandResults.Ok

    @Command("--platform-open", desc="Get the platform open helper")
    def platform_open(self) -> int:
        """Get the platform open helper"""
        if os.name == 'nt' or sys.platform == 'cygwin':
            self.current_output += "start \"\""
        elif sys.platform == 'darwin':
            self.current_output += "open"
        else:
            self.current_output += "xdg-open"
        return CommandResults.Ok
    # </editor-fold>

    # <editor-fold desc="Inputs">
    @Command("--exec", "-e", desc="Run a command", param_names=["COMMAND", "ARGS..."], param_until=";")
    def run_command(self, command: str, *args) -> int:
        """Run a command completely silent but set the output for the next command"""
        result, output = self.exec_cmd(command, args)
        if self.current_output != "":
            self.current_output += "\n"
        self.current_output += output
        if not self.stop_on_error:
            return CommandResults.Ok
        else:
            return result

    @Command("--in", "-i", desc="Set the input", param_names=["STR"])
    def append(self, input: str) -> int:
        """Set the input for the next command"""
        if self.current_output != "":
            self.current_output += "\n"
        input = input.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
        self.current_output += input
        return CommandResults.Ok

    @Command("--read", "-r", desc="Read from a file", param_names=["PATH"])
    def read(self, path: str) -> int:
        """Read the input from a file"""
        try:
            if self.current_output != "":
                self.current_output += "\n"
            with open(path, 'r') as file:
                self.current_output += file.read()
        except OSError as e:
            if self.stop_on_error:
                print(f"Error reading file: {e}")
                return CommandResults.IOError
        return CommandResults.Ok

    @Command("--platform", "-p", desc="Get the platform")
    def platform(self) -> int:
        """Get the platform"""
        if self.current_output != "":
            self.current_output += "\n"

        if os.name == 'nt' or sys.platform == 'cygwin':
            self.current_output += "Windows"
        elif sys.platform == 'linux':
            self.current_output += "Linux"
        elif sys.platform == 'darwin':
            self.current_output += "MacOS"
        else:
            self.current_output += "Unknown"
        return CommandResults.Ok

    @Command("--platform-exec", desc="Get the platform executable extension")
    def platform_exec(self) -> int:
        """Get the platform"""
        if self.current_output != "":
            self.current_output += "\n"

        if os.name == 'nt' or sys.platform == 'cygwin':
            self.current_output += ".exe"
        else:
            self.current_output += ""
        return CommandResults.Ok

    @Command("--platform-open", desc="Get the platform open utility")
    def platform_open(self) -> int:
        """Get the platform"""
        if self.current_output != "":
            self.current_output += "\n"

        if os.name == 'nt' or sys.platform == 'cygwin':
            #self.current_output += "start"
            self.current_output += ""
        elif sys.platform == 'darwin':
            #self.current_output += "open"
            self.current_output += ""
        else:
            self.current_output += ""
        return CommandResults.Ok

    @Command("--cygwin", "-c", desc="Get the Cygwin version")
    def cygwin_version(self) -> int:
        """Get the Cygwin version"""
        if not self.is_cygwin_env():
            print("Not in a Cygwin environment")
            return CommandResults.Not
        try:
            process = subprocess.Popen(["cygcheck", "-c", "cygwin"], stderr=subprocess.DEVNULL, stdout=subprocess.PIPE)
            output, _ = process.communicate()
            if process.returncode != 0:
                return CommandResults.Not
        except Exception as e:
            return CommandResults.Not

        for line in output.decode("utf-8").splitlines():
            if (match := re.match("^cygwin[ \t]+(?P<version>[0-9.-]+)[ \t]+", line)):
                if self.current_output != "":
                    self.current_output += "\n"
                self.current_output += match.group("version")
                return CommandResults.Ok
        return CommandResults.Not

    @Command("--mingw", "-m", desc="Get the MSYS2 version")
    def mingw_version(self) -> int:
        """Get the MSYS2 version"""
        if not self.is_msys2_env():
            print("Not in a MSYS2 environment")
            return CommandResults.Not
        try:
            process = subprocess.Popen(["mingw-get", "--version"], stderr=subprocess.DEVNULL, stdout=subprocess.PIPE)
            output, _ = process.communicate()
            if process.returncode != 0:
                return CommandResults.Not
        except Exception as e:
            return CommandResults.Not

        for line in output.decode("utf-8").splitlines():
            if match := re.match("^mingw-get version[ \t]+(?P<version>[0-9a-z.-]+)[ \t]*", line):
                if self.current_output != "":
                    self.current_output += "\n"
                self.current_output += match.group("version")
                return CommandResults.Ok
        return CommandResults.Not

    @Command("--timestamp", desc="Get the current timestamp")
    def timestamp(self) -> int:
        """Get the current timestamp"""
        if self.current_output != "":
            self.current_output += "\n"
        self.current_output += str(int(datetime.now().timestamp()))
        return CommandResults.Ok
    # </editor-fold>

    # <editor-fold desc="Output Commands">
    def write_to_file(self, path: str, append: bool = False) -> int:
        """Write the input to a file"""
        try:
            dir_path = os.path.dirname(path)
            if dir_path != "":
                os.makedirs(dir_path, exist_ok=True)
        except OSError as e:
            print(f"Error creating directory: {e}")
            return CommandResults.IOError
        try:
            if append:
                with open(path, 'a') as file:
                    file.write(self.current_output + "\n")
            else:
                with open(path, 'w') as file:
                    file.write(self.current_output + "\n")
        except OSError as e:
            print(f"Error writing to file: {e}")
            return CommandResults.IOError
        return CommandResults.Ok

    @Command("--out", "-o", desc="Write to a file", param_names=["PATH"])
    def write_file(self, path: str) -> int:
        return self.write_to_file(path, False)

    @Command("--append", "-a", desc="Append to a file", param_names=["PATH"])
    def append_file(self, path: str) -> int:
        return self.write_to_file(path, True)

    @Command("--print", desc="Print to stdout")
    def print(self) -> int:
        """Print the input to stdout"""
        print(removeprefix(self.current_output, "\n"))
        return CommandResults.Ok
    # </editor-fold>

    # <editor-fold desc="Line-by-Line Processing">
    @Command("--foreach", desc="Run a command for each line", param_names=["COMMAND", "ARGS..."], param_until=";")
    def for_each_line(self, command: str, *args) -> int:
        """Run a command for each line of input"""
        lines = self.current_output.splitlines()
        new_lines = []
        for line in lines:
            result, output = self.exec_cmd(command, args + (line,))
            if result != CommandResults.Ok:
                print(f"Error executing command: {result}")
                return result
            new_lines.append(output)
        self.current_output = "\n".join(new_lines)
        return CommandResults.Ok

    @Command("--include", desc="Include lines from the input", param_names=["FROM", "TO"], param_convert=lambda x: int(x))
    def lines(self, line_from: int, line_to: int) -> int:
        """Get lines from the input"""
        lines = self.current_output.splitlines()
        line_to = len(lines) if line_to == 0 else line_to
        self.current_output = "\n".join(lines[line_from:line_to])
        return CommandResults.Ok

    @Command("--exclude", desc="Exclude lines from the input", param_names=["FROM", "TO"], param_convert=lambda x: int(x))
    def remove_lines(self, line_from: int, line_to: int) -> int:
        """Remove lines from the input"""
        lines = self.current_output.splitlines()
        line_to = len(lines) if line_to == 0 else line_to
        self.current_output = "\n".join(lines[:line_from] + lines[line_to:])
        return CommandResults.Ok

    @Command("--lower", "-l", desc="Convert to lower case")
    def to_lower(self) -> int:
        """Convert the input to lower case"""
        self.current_output = self.current_output.lower()
        return CommandResults.Ok

    @Command("--upper", "-u", desc="Convert to upper case")
    def to_upper(self) -> int:
        """Convert the input to upper case"""
        self.current_output = self.current_output.upper()
        return CommandResults.Ok

    @Command("--filter", "-f", desc="Filter lines based on regex", param_names=["REGEX"])
    def filter_lines(self, pattern: str) -> int:
        """Filter the input lines based on a pattern"""
        try:
            compiled_pattern = re.compile(pattern)
        except re.error:
            print(f"Error compiling regex pattern: {pattern}")
            return CommandResults.RegexError
        lines = self.current_output.splitlines()
        filtered_lines = []
        for line in lines:
            if compiled_pattern.search(line):
                filtered_lines.append(line)
        self.current_output = "\n".join(filtered_lines)
        return CommandResults.Ok

    @Command("--filter-out", desc="Remove lines based on regex", param_names=["REGEX"])
    def remove_lines_regex(self, pattern: str) -> int:
        """Filter the input lines based on a pattern"""
        try:
            compiled_pattern = re.compile(pattern)
        except re.error:
            print(f"Error compiling regex pattern: {pattern}")
            return CommandResults.RegexError
        lines = self.current_output.splitlines()
        filtered_lines = []
        for line in lines:
            if not compiled_pattern.search(line):
                filtered_lines.append(line)
        self.current_output = "\n".join(filtered_lines)
        return CommandResults.Ok

    @Command("--noempty", desc="Remove empty lines")
    def remove_empty_lines(self) -> int:
        """Remove empty lines from the input"""
        lines = self.current_output.splitlines()
        non_empty_lines = [line for line in lines if line.strip() != ""]
        self.current_output = "\n".join(non_empty_lines)
        return CommandResults.Ok

    @Command("--sub", "-s", desc="Replace lines based on regex", param_names=["REGEX", "SUB"], param_count=2)
    def regex_replace(self, pattern: str, replacements: str) -> int:
        """Replace the input lines based on a regex pattern"""
        try:
            compiled_pattern = re.compile(pattern)
        except re.error:
            print(f"Error compiling regex pattern: {pattern}")
            return CommandResults.RegexError
        lines = self.current_output.splitlines()
        new_lines = []
        for line in lines:
            new_lines.append(re.sub(pattern, replacements, line, flags=re.DOTALL))
        self.current_output = "\n".join(new_lines)
        return CommandResults.Ok

    @Command("--sort", desc="Sort lines", param_names=["FLAGS"])
    def sort(self, flags: str) -> int:
        """Sort the input lines based on a type and index"""
        split_flags = flags.split(",")
        column = 0
        reverse = False
        ignore_error_lines = False
        use_numeric = False
        key_func = lambda value: value
        for flag in split_flags:
            if flag == "none":
                pass
            elif flag == "desc":
                reverse = True
            elif flag == "asc":
                reverse = False
            elif flag == "float":
                use_numeric = True
                key_func = lambda value: float(value)
            elif flag == "int":
                use_numeric = True
                key_func = lambda value: int(value)
            elif flag == "int16":
                use_numeric = True
                key_func = lambda value: int(value, 16)
            elif flag == "strip":
                key_func = lambda value: value.strip()
            elif flag == "ignore_error_lines":
                ignore_error_lines = True
            elif flag.startswith("column="):
                flag = removeprefix(flag, "column=")
                try:
                    column = int(flag) - 1
                except Exception as e:
                    try:
                        flag = flag.replace("\\t", "\t").replace("\\n", "\n").replace("\\r", "\r")
                        column = re.compile(removeprefix(removesuffix(removeprefix(removesuffix(flag, "\""), "\""), "'"), "'"))
                    except Exception as e:
                        print(f"Error compiling regex pattern: {flag}: {e}")
                        return CommandResults.InvalidSortColumn
            else:
                print(f"Unknown sort flag: {flag}")
                return CommandResults.InvalidSortFlag

        def get_value(line: str) -> Any:
            if isinstance(column, int):
                split_line = re.split("[ \t]+", line)
                if column >= len(split_line):
                    if ignore_error_lines:
                        if use_numeric:
                            return float("-inf") if reverse else float("inf")
                        else:
                            return ""

                    print(f"Invalid column index: {column} in: {line}")
                    raise Exception(f"Invalid column index: {column} in: {line}")
                else:
                    return key_func(split_line[column])
            elif isinstance(column, re.Pattern):
                if match := column.search(line):
                    try:
                        return key_func(match.group("value"))
                    except Exception as e:
                        if ignore_error_lines:
                            if use_numeric:
                                return float("-inf") if reverse else float("inf")
                            else:
                                return ""
                        raise Exception(f"Error converting regex match: {match.group('value')}: {e}")

                if ignore_error_lines:
                    if use_numeric:
                        return float("-inf") if reverse else float("inf")
                    else:
                        return ""
                raise Exception(f"Failed to find pattern: {column} in: {line}")

        lines = self.current_output.splitlines()
        # Validate the input first, we'll perform the same processing twice but at least we get feedback
        for line in lines:
            try:
                get_value(line)
            except Exception as e:
                print(f"Error converting value: {column} in: {line}: {e}")
                return CommandResults.InvalidSortValue

        lines = sorted(lines, key=lambda line: get_value(line), reverse=reverse)
        self.current_output = "\n".join(lines)
        return CommandResults.Ok

    @Command("--unique", desc="Remove duplicate lines")
    def unique(self) -> int:
        """Remove duplicate lines from the input"""
        lines = self.current_output.splitlines()
        unique_lines = []
        for line in lines:
            if line != unique_lines[-1]:
                unique_lines.append(line)
        self.current_output = "\n".join(unique_lines)
        return CommandResults.Ok

    @Command("--reverse", desc="Reverse lines")
    def reverse_lines(self) -> int:
        """Reverse the input lines"""
        lines = self.current_output.splitlines()
        lines.reverse()
        self.current_output = "\n".join(lines)
        return CommandResults.Ok

    @Command("--first", desc="Get the first line")
    def first_line(self) -> int:
        """Get the first line of the input"""
        lines = self.current_output.splitlines()
        if len(lines) > 0:
            self.current_output = lines[0]
        else:
            self.current_output = ""
        return CommandResults.Ok

    @Command("--last", desc="Get the last line")
    def last_line(self) -> int:
        """Get the last line of the input"""
        lines = self.current_output.splitlines()
        if len(lines) > 0:
            self.current_output = lines[-1]
        else:
            self.current_output = ""
        return CommandResults.Ok

    @Command("--sum", desc="Sum lines", param_names=["FLAGS"])
    def sum_lines(self, flags) -> int:
        """Sum the input lines"""
        split_flags = flags.split(",")
        column = 0
        ignore_error_lines = False
        key_func = lambda value: float(value)
        out_func = lambda value: f"{value:f}"
        for flag in split_flags:
            if flag == "none" or flag == "float":
                pass
            elif flag == "int16":
                key_func = lambda value: int(value, 16)
                out_func = lambda value: f"{value:x}"
            elif flag == "int":
                key_func = lambda value: int(value)
                out_func = lambda value: f"{value:d}"
            elif flag.startswith("float="):
                flag = removeprefix(flag, "float=")
                out_func = lambda value: f"{value:.{flag}f}"
            elif flag == "ignore_error_lines":
                ignore_error_lines = True
            elif flag.startswith("column="):
                flag = removeprefix(flag, "column=")
                try:
                    column = int(flag) - 1
                except Exception as e:
                    try:
                        flag = flag.replace("\\t", "\t").replace("\\n", "\n").replace("\\r", "\r")
                        column = re.compile(
                            removeprefix(removesuffix(removeprefix(removesuffix(flag, "\""), "\""), "'"), "'"))
                    except Exception as e:
                        print(f"Error compiling regex pattern: {flag}: {e}")
                        return CommandResults.InvalidSortColumn
            else:
                print(f"Unknown sum flag: {flag}")
                return CommandResults.InvalidSumFlag
        def get_value(line: str) -> Any:
            if isinstance(column, int):
                split_line = re.split("[ \t]+", line)
                if column >= len(split_line):
                    if ignore_error_lines:
                        return 0

                    print(f"Invalid column index: {column} in: {line}")
                    raise Exception(f"Invalid column index: {column} in: {line}")
                else:
                    return key_func(split_line[column])
            elif isinstance(column, re.Pattern):
                if match := column.search(line):
                    try:
                        return key_func(match.group("value"))
                    except Exception as e:
                        if ignore_error_lines:
                            return 0
                        raise Exception(f"Error converting regex match: {match.group('value')}: {e}")

                if ignore_error_lines:
                    return 0
                raise Exception(f"Failed to find pattern: {column} in: {line}")

        lines = self.current_output.splitlines()
        # Validate the input first, we'll perform the same processing twice but at least we get feedback
        for line in lines:
            try:
                get_value(line)
            except Exception as e:
                print(f"Error converting value: {column} in: {line}: {e}")
                return CommandResults.InvalidSumValue

        result = sum(get_value(line) for line in lines)
        self.current_output = out_func(result)
        return CommandResults.Ok

    @Command("--count", desc="Count lines")
    def count_lines(self) -> int:
        """Count the number of lines in the input"""
        lines = self.current_output.splitlines()
        self.current_output = str(len(lines))
        return CommandResults.Ok
    # </editor-fold>

    # <editor-fold desc="File System Commands">
    def is_cygwin_env(self):
        """Check if we are in a Cygwin environment"""
        return os.path.isdir("/cygdrive")
    def is_msys2_env(self):
        """Check if we are in a MSYS2 environment"""
        return (
                os.environ.get("MSYSTEM") is not None or
                os.path.exists("/mingw64") or
                os.path.exists("/mingw32") or
                os.environ.get("MSYS", "").lower() == "true")

    @Command("--env-path", desc="Convert to environment path")
    def env_path(self) -> int:
        """Convert the input to a make path, basically do nothing unless we are on Windows. If we are,
        convert to /cygdrive/c/path/to/file if we are in a Cygwin environment, or /c/path/to/file if
        we are in a MSYS2 environment, otherwise just convert \\ to /"""
        if os.name == 'nt' or sys.platform == 'cygwin':
            lines = self.current_output.splitlines()
            new_lines = []
            for line in lines:
                line = line.strip().replace("\\", "/")
                if match := self.win_path_re.match(line):
                    drive = match.group("drive").lower()
                    path = match.group("path")
                    if self.is_cygwin_env():
                        line = f"/cygdrive/{drive}/{path}"
                    elif self.is_msys2_env():
                        line = f"/{drive}/{path}"
                    new_lines.append(removesuffix(line.replace("//", "/"), "/"))
            self.current_output = "\n".join(new_lines)
        return CommandResults.Ok

    @Command("--platform-path", desc="Convert to platform path")
    def platform_path(self) -> int:
        """Convert the input to an argument path"""
        if os.name == 'nt' or sys.platform == 'cygwin':
            lines = self.current_output.splitlines()
            new_lines = []
            for line in lines:
                line = line.strip().replace("\\", "/")
                if self.is_cygwin_env():
                    if match := self.cygwin_path_re.match(line):
                        drive = match.group("drive").lower()
                        path = match.group("path")
                        line = f"{drive}:/{path}"
                elif self.is_msys2_env():
                    if match := self.msys2_path_re.match(line):
                        drive = match.group("drive").lower()
                        path = match.group("path")
                        line = f"{drive}:/{path}"
                new_lines.append(line)
            self.current_output = "\n".join(new_lines)
        return CommandResults.Ok

    @Command("--shell-list", desc="Convert to shell list")
    def shell_list(self) -> int:
        """Convert the input to a shell list"""
        lines = self.current_output.splitlines()
        if os.name == 'nt' and not self.is_cygwin_env():
            self.current_output = ";".join(lines)
        else:
            self.current_output = ":".join(lines)
        return CommandResults.Ok

    @Command("--dirname", desc="Get the directory name")
    def dirname(self) -> int:
        """Get the directory name of the input"""
        lines = self.current_output.splitlines()
        new_lines = []
        for line in lines:
            new_lines.append(os.path.dirname(line.strip()))
        self.current_output = "\n".join(new_lines)
        return CommandResults.Ok
    @Command("--basename", desc="Get the base name")
    def basename(self) -> int:
        """Get the base name of the input"""
        lines = self.current_output.splitlines()
        new_lines = []
        for line in lines:
            new_lines.append(os.path.basename(line.strip()))
        self.current_output = "\n".join(new_lines)
        return CommandResults.Ok

    @Command("--touch", desc="Create a file or update its timestamp", param_names=["PATH"])
    def touch(self, path: str) -> int:
        """Create a file or update its timestamp"""
        try:
            with open(path, 'a'):
                pass
            os.utime(path, None)
        except OSError as e:
            print(f"Error creating file: {e}")
            return CommandResults.IOError
        return CommandResults.Ok

    @Command("--symlink", desc="Create a symbolic link", param_names=["TARGET", "LINK"])
    def symlink(self, target: str, link_name: str) -> int:
        """
        Creates a symbolic link (or copy on Windows if no admin rights)
        - TARGET: Target file/directory to link to
        - LINK_NAME: Name of the link to create
        """
        try:
            os.symlink(target, link_name)
        except (OSError, AttributeError):
            if os.path.isdir(target):
                if os.path.exists(link_name):
                    shutil.rmtree(link_name)
                shutil.copytree(target, link_name)
            else:
                shutil.copy2(target, link_name)
        return CommandResults.Ok
    @Command("--ensure-dir", desc="Create a directory", param_names=["PATH"])
    def ensure_dir_explicit(self, path: str) -> int:
        """Create a directory"""
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            print(f"Error creating directory: {e}")
            return CommandResults.IOError
        return CommandResults.Ok
    @Command("--ensure-dirs", desc="Create directories for all target lines", param_names=["PATH"])
    def ensure_dirs(self, path: str) -> int:
        """Create a directory"""
        lines = self.current_output.splitlines()
        for line in lines:
            path = line.strip()
            if path != "" and not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                except OSError as e:
                    print(f"Error creating directory: {e}")
                    return CommandResults.IOError
                return CommandResults.Ok

    @Command("--glob", desc="Unpack glob patterns in lines")
    def glob_lines(self) -> int:
        """Unpack glob patterns in lines"""
        lines = self.current_output.splitlines()
        new_lines = []
        for line in lines:
            results = glob.glob(line)
            if len(results) > 0:
                new_lines.extend(results)
            elif self.stop_on_error:
                print(f"Error: No files found for pattern: {line}")
                return CommandResults.CommandNotFoundError
        self.current_output = "\n".join(new_lines)
        return CommandResults.Ok

    @Command("--exists", desc="Check if all files exist")
    def exists(self) -> int:
        """Check if all files exist"""
        lines = self.current_output.splitlines()
        new_lines = []
        for line in lines:
            result = glob.glob(line.strip())
            if len(result) > 0:
                new_lines.append("true")
        self.current_output = "\n".join(new_lines)
        return CommandResults.Ok

    @Command("--print-valid", desc="Print valid files or directories", param_names=["FLAGS"])
    def print_valid(self, flags) -> int:
        """Print valid files or directories"""
        split_flags = flags.split(",")
        check_func = os.path.exists
        for flag in split_flags:
            if flag == "all":
                pass
            elif flag == "dir":
                check_func = os.path.isdir
            elif flag == "file":
                check_func = os.path.isfile
            elif flag == "symlink":
                check_func = os.path.islink
            else:
                print(f"Unknown filter flag: {flag}")
                return CommandResults.InvalidFilterFlag

        lines = self.current_output.splitlines()
        new_lines = []
        for line in lines:
            if check_func(line.strip()):
                new_lines.append(line)
        self.current_output = "\n".join(new_lines)
        return CommandResults.Ok
    # </editor-fold>

    # <editor-fold desc="Command Line Parsing">
    def parse_command(self, arg_long: str = None, arg_short: str = None, requires: int = 0) -> bool:
        arg = self.args[0]
        if arg.startswith(arg_long):
            arg = removeprefix(arg, arg_long)
            if arg.startswith("="):
                arg = removeprefix(arg, "=")
                self.args[0] = arg
            elif arg == "":
                self.args.pop(0)
            else:
                return False
        elif arg == arg_short:
            self.args.pop(0)
        else:
            return False

        if len(self.args) < requires:
            raise ParameterCountError(f"Not enough parameters for {arg_long} or {arg_short}")
        return True

    def parse_command_params(self, command: Command) -> List[str]:
        """Parse the arguments for a command"""
        if command.param_count >= 0:
            args = self.args[:command.param_count]
        else:
            args = list(self.args)
        if command.param_until and command.param_until not in args:
            raise ParameterCountError(f"Missing {command.param_until} terminator for {command.arg_long}")
        elif command.param_until and (separator_index := args.index(command.param_until)) >= 0:
            args = args[:separator_index]
            self.args = self.args[len(args) + 1:]
        else:
            self.args = self.args[len(args):]
        if command.param_convert:
            return [command.param_convert(arg) for arg in args]
        else:
            return args

    def parse_commands(self) -> int:
        """Process the input based on the command line arguments"""
        result = CommandResults.NoCommands
        command = None
        args = None
        while len(self.args) > 0:
            try:
                result = CommandResults.UnknownArgument
                for name, value in self.__class__.__dict__.items():
                    if hasattr(value, 'command_attrs'):
                        command = value.command_attrs
                        if self.parse_command(command.arg_long, command.arg_short, command.param_count):
                            args = self.parse_command_params(command)
                            result = command.func(self, *args)
                            #print(f"Executing command: {command.arg_long} {args}, remaining {self.args}")
                            break
                if result == CommandResults.UnknownArgument:
                    print(f"Error: Unknown command: {self.args[0]}")
                    return result
            except ParameterCountError as e:
                print(f"Error: {e}")
                return CommandResults.MissingParameter
            if result != CommandResults.Ok and self.stop_on_error:
                print(f"Failed to execute command: {command.arg_long if command else ''} {' '.join(args) if args else ''} with result: {result}")
                break

        if result == CommandResults.NoCommands:
            print("No commands found")
            self.print_help()
        return result
    # </editor-fold>

if __name__ == "__main__":
    processor = CommandProcessor(sys.argv)
    sys.exit(processor.parse_commands())