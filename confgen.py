#!/usr/bin/env python3

"""
DOSBox configuration file generator.
"""

import argparse
import configparser
import hashlib
import os
import pathlib
import re

import midi

from toolbox import print_err

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

SBLASTER_SECTION = """
[sblaster]
sbtype=sb16
sbbase={base}
irq={irq}
dma={dma}
hdma={hdma}

""".lstrip()

SBLASTER_INFO = """
Digital Sound: Sound Blaster 16
    Base Port: {base}
          IRQ: {irq}
          DMA: {dma}
""".strip()

MIDI_SECTION = """
[midi]
mpu401=intelligent
mididevice=default
midiconfig={port}

""".lstrip()

# Port 330 is hard-coded in DOSBox
MIDI_INFO = """
        Music: General MIDI (MPU-401 compatible)
         Port: 330
"""[1:]

MIDI_INFO_NA = """
        Music: No MIDI synthesiser found
"""[1:]


# pylint: disable=too-few-public-methods
# We need this class to cache file paths in future.
class FileTree:
    """Provide access to a file tree using Windows paths."""

    def __init__(self, root):
        self.root = root

    def get_posix_path(self, path):
        """Return real file referenced by case-insensitive Windows path."""
        assert self.root
        return to_posix_path(path)


class DosboxConfiguration(dict):

    """Class representing DOSBox configuration.

    Autoexec section represents commands from default .conf files,
    files referenced by -conf argument, commands injected with -c argument
    and commands usually generated by DOSBox itself.

    Other sections of raw configuration represent relevant sections
    found in configuration files.  Values inside sections override
    values seen in previous configuration files.
    """

    def __init__(self, *, pfx='.', commands=[], conf_files=[], exe=None,
                 noautoexec=False, exit_after_exe=False):
        assert commands or conf_files or exe
        dict.__init__(self)
        self['autoexec'] = []
        self.raw_autoexec = self['autoexec']
        self.file_tree = FileTree(pfx)

        for win_path in (conf_files or self.__get_default_conf__()):
            path = self.file_tree.get_posix_path(win_path)
            conf = parse_dosbox_config(path)
            self.__import_ini_sections__(conf)
            if not noautoexec and conf.has_section('autoexec'):
                self.raw_autoexec.extend(line for line in conf['autoexec'])

        self.raw_autoexec.extend(cmd for cmd in commands)

        if exe:
            posix_path = self.file_tree.get_posix_path(exe)
            path, file = os.path.split(posix_path)
            self.raw_autoexec.append(f'mount C {path or "."}')
            self.raw_autoexec.append('C:')
            if file.lower().endswith('.bat'):
                self.raw_autoexec.append(f'call {file}')
            else:
                self.raw_autoexec.append(file)
            if exit_after_exe:
                self.raw_autoexec.append('exit')

    def __get_default_conf__(self):
        path = self.file_tree.get_posix_path('dosbox.conf')
        if path and os.path.isfile(path):
            return [path]
        return []

    def __import_ini_sections__(self, config):
        for name in config.sections():
            if name == 'autoexec':
                continue
            if not self.has_section(name):
                self[name] = config[name]
                continue
            for opt, val in config[name].items():
                self.set(name, opt, val)

    def sections(self):
        """Return a list of section names."""
        return list(self.keys())

    def has_section(self, section):
        "Indicates whether the named section is present in the configuration."
        return section in self.keys()

    def set(self, section, option, value):
        """Set option in section to value.

        If the given section exists, set the given option to the specified
        value; otherwise raise NoSectionError.
        """
        if section not in self:
            raise configparser.NoSectionError
        self[section][option] = value


def uniq_conf_name(app_id, args):
    """Return unique .conf file name for given SteamAppId and arguments."""
    uid_line = app_id + ''.join(args)
    uid = hashlib.sha1(uid_line.encode('utf-8')).hexdigest()[:6]
    return f'steam_dos_{app_id}_{uid}.conf'


def parse_dosbox_config(conf_file):
    """Parse DOSBox configuration file."""
    if conf_file is None:
        return None
    config = configparser.ConfigParser(allow_no_value=True,
                                       delimiters='=',
                                       strict=False)
    config.optionxform = str
    try:
        # Try simply reading a .conf file, assuming it's utf-8 encoded,
        # as any modern text editor will likely create utf-8 file by
        # default.
        #
        config.read(conf_file)

    except UnicodeDecodeError:
        # Failed decoding from utf-8 means, that likely there are some
        # graphical glyphs in autoexec section of a .conf file.
        #
        # This seems to be a common case for .conf files distributed
        # with GOG games. Just retry with specific old encoding.
        #
        config.read(conf_file, encoding='cp1250')

    return config


def to_linux_autoexec(autoexec):
    """Convert case-sensitive parts in autoexec."""
    cmd_1 = r'@? *(mount|imgmount) +([a-z]):? +"([^"]+)"( +(.*))?'
    cmd_2 = r'@? *(mount|imgmount) +([a-z]):? +([^ ]+)( +(.*))?'
    mount_cmd_1 = re.compile(cmd_1, re.IGNORECASE)
    mount_cmd_2 = re.compile(cmd_2, re.IGNORECASE)
    change_drv = re.compile(r'@? *([a-z]:)\\? *$', re.IGNORECASE)
    tree = FileTree('.')
    for line in autoexec:
        match = mount_cmd_1.match(line) or mount_cmd_2.match(line)
        if match:
            cmd = match.group(1).lower()
            drive = match.group(2).upper()
            win_path = match.group(3)
            rest = match.group(4) or ''
            path = tree.get_posix_path(win_path)
            yield f'{cmd} {drive} "{path}"{rest}'
            continue
        match = change_drv.match(line)
        if match:
            drive = match.group(1).upper()
            yield f'{drive}'
            continue
        yield line


def parse_dosbox_arguments(args):
    """Parse subset of DOSBox command line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-conf', action='append')
    parser.add_argument('-c', action='append', nargs='?')
    parser.add_argument('-noautoexec', action='store_true')
    parser.add_argument('-noconsole', action='store_true')
    parser.add_argument('-fullscreen', action='store_true')
    parser.add_argument('-exit', action='store_true')
    parser.add_argument('file', nargs='?')
    args = parser.parse_args(args)
    cmds = list(filter(lambda x: x, args.c))
    args.c = cmds
    return args


def create_conf_file(name, dosbox_args):
    """Create DOSBox configuration file.

    Different sections are chosen either by this module, copied from
    existing .conf files, generated based on '-c' DOSBox argument or
    generated from a file pointed to be run.
    """
    assert name
    args = parse_dosbox_arguments(dosbox_args)
    conf = DosboxConfiguration(conf_files=(args.conf or []),
                               commands=args.c,
                               exe=args.file,
                               noautoexec=args.noautoexec,
                               exit_after_exe=args.exit)
    with open(name, 'w') as conf_file:
        conf_file.write(COMMENT_SECTION.format(dosbox_args))
        conf_file.write(SDL_SECTION.format(dosbox_args))
        if conf.has_section('mixer'):
            conf_file.write('[mixer]\n')
            for key, val in conf['mixer'].items():
                conf_file.write(f'{key}={val}\n')
            conf_file.write('\n')
        if conf.has_section('autoexec'):
            conf_file.write('[autoexec]\n')
            for line in to_linux_autoexec(conf['autoexec']):
                conf_file.write(line + '\n')


def create_audio_conf():
    """Create DOSBox audio configuration."""
    name = 'steam_dos_audio.conf'

    mport = midi.detect_software_synthesiser(r'timidity|fluid')
    if mport:
        print_err(f'steam-dos: Detected {mport.name} on {mport.addr}')

    with open(name, 'w') as audio:
        audio.write('# Generated by steam-dos\n')
        audio.write('# This file is re-created on every run\n')
        audio.write('\n')
        base, irq, dma, hdma = 220, 7, 1, 5  # DOSBox defaults
        print_err('steam-dos: Setting up DOSBox audio:')
        print_err(SBLASTER_INFO.format(base=base, irq=irq, dma=dma))
        audio.write(SBLASTER_SECTION.format(base=base, irq=irq,
                                            dma=dma, hdma=hdma))
        if mport:
            print_err(MIDI_INFO)
            audio.write(MIDI_SECTION.format(port=mport.addr))
        else:
            print_err(MIDI_INFO_NA)
    return name


def to_posix_path(windows_path_str):
    """Convert a string representing case-insensitive path to a string
    representing path to existing file.
    """
    if windows_path_str == '.':
        return '.'
    win_path = pathlib.PureWindowsPath(windows_path_str)
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
    # TODO rewrite this in more time-effective manner for worst case scenario.
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
