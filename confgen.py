#!/usr/bin/env python3

"""
DOSBox configuration file generator.
"""

import argparse
import configparser
import hashlib
import os
import re

import midi

from settings import SETTINGS as settings
from toolbox import print_err
from winpathlib import to_posix_path

COMMENT_SECTION = """
# Generated by steam-dos
# Based on args to Windows version of DOSBox:
# {}

""".lstrip()

SDL_SECTION_1 = """
[sdl]
fullscreen=true
fullresolution={resolution}
output=opengl
autolock=false
waitonerror=true

""".lstrip()

SDL_SECTION_2 = """
[sdl]
# fullscreen=true
# output=opengl
# autolock=false

""".lstrip()

RENDER_SECTION_1 = """
[render]
aspect={aspect}
scaler={scaler}

""".lstrip()

RENDER_SECTION_2 = """
[render]
# aspect: Do aspect correction for games using 320x200 resolution.
#         Read more: https://www.dosbox.com/wiki/Dosbox.conf#aspect
# scaler: Specifies which scaler is used to enlarge and enhance low resolution
#         modes, before any scaling done through OpenGL.
#         Read more: https://www.dosbox.com/wiki/Dosbox.conf#scaler
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

DOS_SECTION = """
[dos]
xms={xms}
ems={ems}
umb={umb}

""".lstrip()

# Port 330 is hard-coded in DOSBox
MIDI_INFO = """
        Music: General MIDI (MPU-401 compatible)
         Port: 330
""" [1:]

MIDI_INFO_NA = """
        Music: No MIDI synthesiser found
""" [1:]


class DosboxConfiguration(dict):
    """Class representing DOSBox configuration.

    Autoexec section represents commands from default .conf files,
    files referenced by -conf argument, commands injected with -c argument
    and commands usually generated by DOSBox itself.

    Other sections of raw configuration represent relevant sections
    found in configuration files.  Values inside sections override
    values seen in previous configuration files.
    """

    def __init__(self,
                 *,
                 commands=[],
                 conf_files=[],
                 exe=None,
                 noautoexec=False,
                 exit_after_exe=False,
                 tweak_conf={}):
        assert commands or conf_files or exe
        dict.__init__(self)
        self['autoexec'] = []
        self.raw_autoexec = self['autoexec']
        self.encoding = 'utf-8'

        for win_path in (conf_files or self.__get_default_conf__()):
            path = to_posix_path(win_path)
            conf, enc = parse_dosbox_config(path)
            self.__import_ini_sections__(conf)
            if enc != 'utf-8':
                self.encoding = enc
            if not noautoexec and conf.has_section('autoexec'):
                self.raw_autoexec.extend(line for line in conf['autoexec'])

        self.raw_autoexec.extend(cmd for cmd in commands)

        tweak = configparser.ConfigParser()
        tweak.read_dict(tweak_conf)
        self.__import_ini_sections__(tweak)

        if exe:
            posix_path = to_posix_path(exe)
            path, file = os.path.split(posix_path)
            self.raw_autoexec.append('mount C {0}'.format(path or '.'))
            self.raw_autoexec.append('C:')
            if file.lower().endswith('.bat'):
                self.raw_autoexec.append('call {0}'.format(file))
            else:
                self.raw_autoexec.append(file)
            if exit_after_exe:
                self.raw_autoexec.append('exit')

    def __get_default_conf__(self):
        # pylint: disable=no-self-use
        path = to_posix_path('dosbox.conf')
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


def cleanup_old_conf_files(app_id, args):
    """Remove old unused, versions of .conf files."""
    for name in 'steam_dos_audio.conf', uniq_conf_name_v0(app_id, args):
        if os.path.isfile(name):
            os.remove(name)


def uniq_conf_name(app_id, args):
    """Return unique .conf file name for given SteamAppId and arguments."""
    return uniq_conf_name_salted(app_id, args, 'v1')


def uniq_conf_name_v0(app_id, args):
    """Return unique .conf file name for given SteamAppId and arguments."""
    return uniq_conf_name_salted(app_id, args, '')


def uniq_conf_name_salted(app_id, args, salt):
    """Implements .conf name generator."""
    uid_line = app_id + ''.join(args) + salt
    uid = hashlib.sha1(uid_line.encode('utf-8')).hexdigest()[:6]
    return 'steam_dos_{0}_{1}.conf'.format(app_id, uid)


def parse_dosbox_config(conf_file):
    """Parse DOSBox configuration file."""
    assert conf_file
    config = configparser.ConfigParser(allow_no_value=True,
                                       delimiters='=',
                                       strict=False)
    config.optionxform = str
    encoding = 'utf-8'
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
        encoding = 'cp1250'
        config.read(conf_file, encoding=encoding)

    return config, encoding


def to_linux_autoexec(autoexec):
    """Convert case-sensitive parts in autoexec."""
    cmd_1 = r'@? *(mount|imgmount) +([a-z]):? +"([^"]+)"( +(.*))?'
    cmd_2 = r'@? *(mount|imgmount) +([a-z]):? +([^ ]+)( +(.*))?'
    mount_cmd_1 = re.compile(cmd_1, re.IGNORECASE)
    mount_cmd_2 = re.compile(cmd_2, re.IGNORECASE)
    change_drv = re.compile(r'@? *([a-z]:)\\? *$', re.IGNORECASE)
    for line in autoexec:
        match = mount_cmd_1.match(line) or mount_cmd_2.match(line)
        if match:
            cmd = match.group(1).lower()
            drive = match.group(2).upper()
            path = to_posix_path(match.group(3))
            rest = match.group(4) or ''
            yield '{0} {1} "{2}"{3}'.format(cmd, drive, path, rest)
            continue
        match = change_drv.match(line)
        if match:
            drive = match.group(1).upper()
            yield drive
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
    cmds = list(filter(lambda x: x, args.c or []))
    args.c = cmds
    return args


def create_dosbox_configuration(dosbox_args, tweak_conf):
    """Interpret DOSBox configuration."""
    args = parse_dosbox_arguments(dosbox_args)
    conf = DosboxConfiguration(conf_files=(args.conf or []),
                               commands=args.c,
                               exe=args.file,
                               noautoexec=args.noautoexec,
                               exit_after_exe=args.exit,
                               tweak_conf=tweak_conf)
    return conf


def create_user_conf_file(name, conf, dosbox_args):
    """Create DOSBox configuration file for user.

    Different sections are chosen either by this module, copied from
    existing .conf files, generated based on '-c' DOSBox argument or
    generated from a file pointed to be run.
    """
    assert name
    with open(name, 'w', encoding=conf.encoding) as conf_file:
        conf_file.write(COMMENT_SECTION.format(dosbox_args))
        conf_file.write(SDL_SECTION_2)
        if conf.has_section('mixer'):
            conf_file.write('[mixer]\n')
            for key, val in conf['mixer'].items():
                conf_file.write('{0}={1}\n'.format(key, val))
            conf_file.write('\n')

        if conf.has_section('render'):
            conf_file.write(RENDER_SECTION_2)
            for key, val in conf['render'].items():
                if key == 'frameskip':
                    # This option is useless nowadays, let's hide it.
                    continue
                if key in ('scaler', 'aspect'):
                    # Publishers sometimes pick weird scalers by default.
                    # We don't want their choice, but let's signal to the
                    # user, that here's the place to override the value.
                    #
                    # Same goes for aspect - it's common for publishers
                    # to misconfigure it and we inject game-specific
                    # default to auto.conf already.
                    #
                    conf_file.write('# {0}={1}\n'.format(key, val))
                    continue
                conf_file.write('{0}={1}\n'.format(key, val))
            conf_file.write('\n')

        if conf.has_section('autoexec'):
            conf_file.write('[autoexec]\n')
            for line in to_linux_autoexec(conf['autoexec']):
                conf_file.write(line + '\n')


def create_auto_conf_file(conf):
    """Create DOSBox configuration file based on environment.

    Different sections are either hard-coded or generated based on
    user environment (used midi port, current screen resolution, etc.).
    """

    name = 'steam_dos_auto.conf'

    mport = midi.detect_software_synthesiser(r'timidity|fluid')
    if mport:
        print_err('steam-dos: Detected', mport.name, 'on', mport.addr)

    with open(name, 'w') as auto:
        auto.write('# Generated by steam-dos\n')
        auto.write('# This file is re-created on every run\n')
        auto.write('\n')

        sdl_fullresolution = settings.get_dosbox_fullresolution()
        auto.write(SDL_SECTION_1.format(resolution=sdl_fullresolution))

        render_scaler = settings.get_dosbox_scaler()
        render_aspect = 'false'
        if conf and conf.has_section('render'):
            render_aspect = conf['render'].get('aspect', 'false')
        auto.write(
            RENDER_SECTION_1.format(scaler=render_scaler,
                                    aspect=render_aspect))

        base, irq, dma, hdma = 220, 7, 1, 5  # DOSBox defaults
        print_err('steam-dos: Setting up DOSBox audio:')
        print_err(SBLASTER_INFO.format(base=base, irq=irq, dma=dma))
        auto.write(SBLASTER_SECTION.format(base=base, irq=irq, dma=dma,
                                           hdma=hdma))  # yapf: disable
        if mport:
            print_err(MIDI_INFO)
            auto.write(MIDI_SECTION.format(port=mport.addr))
        else:
            print_err(MIDI_INFO_NA)

        if conf and conf.has_section('dos'):
            dos_xms = conf['dos'].get('xms', 'true')
            dos_ems = conf['dos'].get('ems', 'true')
            dos_umb = conf['dos'].get('umb', 'true')
            auto.write(DOS_SECTION.format(xms=dos_xms,
                                          ems=dos_ems,
                                          umb=dos_umb))  # yapf: disable

    return name
