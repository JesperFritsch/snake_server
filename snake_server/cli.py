import argparse
import logging

LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}

def log_level_type(level_name):
    try:
        # Convert the string to uppercase and get the log level
        return LOG_LEVELS[level_name.upper()]
    except KeyError:
        raise argparse.ArgumentTypeError(f"Invalid log level: {level_name}")

def cli(sys_argv):
    parser = argparse.ArgumentParser("Run the snake server")
    parser.add_argument("--port", type=int, default=42069)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument(
        "--log-level",
        type=log_level_type,
        default="DEBUG",
        help=f"Set the log level for the server: ({', '.join(LOG_LEVELS.keys())})",)
    return parser.parse_args(sys_argv)
