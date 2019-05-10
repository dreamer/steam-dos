#!/usr/bin/env python3

# pylint: disable=fixme

"""
Module documentation
"""

import argparse
import configparser
import hashlib
import os
import pathlib

COMMENT_SECTION = """
# Generated by steam-dos
# Based on args to Windows version of DOSBox:
# {}
""".lstrip()

SDL_SECTION = """
[sdl]
fullscreen=true
fullresolution=desktop
output=opengl
autolock=false
waitonerror=true
""".lstrip()


def uniq_conf_name(app_id, args):
    """Return unique .conf file for given SteamAppId and dosbox args."""
    uid_line = app_id + ''.join(args)
    uid = hashlib.sha1(uid_line.encode('utf-8')).hexdigest()[:6]
    return f'steam_dos_{app_id}_{uid}.conf'


def parse_dosbox_config(conf_file):
    if conf_file is None:
        return None
    config = configparser.ConfigParser(allow_no_value=True, delimiters='=')
    config.optionxform = str
    config.read(conf_file)
    return config


def convert_autoexec_section(config):
    dos_drives = {}
    active_path = '.'
    for line in config['autoexec']:
        words = line.split()  # FIXME quoting, maybe proper parser
        cmd = words[0].lower()
        if cmd == 'exit':
            continue
        if cmd == 'mount':
            drive = words[1][0].upper()
            path = to_posix_path(active_path, words[2]) or '.'
            dos_drives[drive] = path
            yield ' '.join(['mount', drive, path] + words[3:])
            continue
        if len(cmd) == 2 and cmd[0].isalpha() and cmd[1] == ':':
            drive = cmd[0].upper()
            active_path = dos_drives[drive]
            yield f'{drive}:'
            continue
        yield line
    yield 'exit'  # add 'exit' for games, that passed it through cmd line param


def create_conf_file(name, dosbox_args):
    assert name

    parser = argparse.ArgumentParser()
    parser.add_argument('-conf')
    parser.add_argument('-c', action='append')
    parser.add_argument('-fullscreen', action='store_true')
    parser.add_argument('-exit', action='store_true')
    parser.add_argument('file', nargs='?')
    args = parser.parse_args(dosbox_args)

    exe_file = to_posix_path('.', args.file) if args.file else ''
    orig_conf_file = to_posix_path('.', args.conf) if args.conf else ''
    fallback_conf_file = to_posix_path('.', 'dosbox.conf')
    dos_commands = args.c if args.c else []

    assert exe_file or orig_conf_file

    original_config = parse_dosbox_config(orig_conf_file)
    fallback_config = parse_dosbox_config(fallback_conf_file)

    with open(name, 'w') as conf_file:
        conf_file.write(COMMENT_SECTION.format(dosbox_args))
        conf_file.write('\n')
        conf_file.write(SDL_SECTION.format(dosbox_args))
        conf_file.write('\n')

        # TODO remove code duplication from fallback_config

        if original_config and original_config.has_section('mixer'):
            conf_file.write(f'# Section copied from {orig_conf_file}\n')
            conf_file.write('[mixer]\n')
            for key, val in original_config['mixer'].items():
                conf_file.write(f'{key}={val}\n')
            conf_file.write('\n')
        elif fallback_config and fallback_config.has_section('mixer'):
            conf_file.write(f'# Section copied from {fallback_conf_file}\n')
            conf_file.write('[mixer]\n')
            for key, val in fallback_config['mixer'].items():
                conf_file.write(f'{key}={val}\n')
            conf_file.write('\n')

        if dos_commands:
            conf_file.write(f'# Section forced through -c arguments\n')
            conf_file.write('[autoexec]\n')
            for line in dos_commands:
                conf_file.write(line + '\n')
            conf_file.write('exit\n')
        elif exe_file:
            conf_file.write(f'# Section generated for {exe_file}\n')
            conf_file.write('[autoexec]\n')
            folder, exe = os.path.split(exe_file)
            conf_file.write(f'mount C {folder}\n')
            conf_file.write('C:\n')
            conf_file.write(f'{exe}\n')
            conf_file.write('exit\n')
        else:
            conf_file.write(f'# Section adapted from {orig_conf_file}\n')
            conf_file.write('[autoexec]\n')
            for line in convert_autoexec_section(original_config):
                conf_file.write(line + '\n')


def to_posix_path(prefix, windows_path_str):
    """Convert a string representing case-insensitive path to a string
    representing path to existing file.
    """
    win_path = pathlib.PureWindowsPath(prefix + '\\' + windows_path_str)
    posix_parts = to_posix_parts(win_path.parts)
    if posix_parts is None:
        return None
    if posix_parts == ():
        return ''
    return os.path.join(*posix_parts)


def guess(part):
    """Generate all the possible capitalizations of given string,
    starting with the most probable ones.
    """
    yield part
    yield part.upper()
    yield part.lower()
    yield part.capitalize()

    def switch_cases(txt):
        if not txt:
            return ['']
        letter = txt[0]
        rest = switch_cases(txt[1:])
        return [letter.upper() + suffix for suffix in rest] + \
               [letter.lower() + suffix for suffix in rest]

    for candidate in switch_cases(part):
        yield candidate


def to_posix_parts(parts):
    """Return posix path representing existing file referenced in
    case-insensitive path passed as tuple.

    Works with assumption, that existing file is unique.
    """
    # FIXME rewrite this in more time-effective manner for worst case scenario.
    if parts is None:
        return None
    if parts == ():
        return parts
    prefix_parts, last_part = parts[:-1], parts[-1]
    prefix = to_posix_parts(prefix_parts)
    if prefix is None:
        return None
    for case_sensitive_part in guess(last_part):
        case_sensitive_parts = prefix + (case_sensitive_part,)
        if os.path.exists(os.path.join(*case_sensitive_parts)):
            return case_sensitive_parts
    return None
