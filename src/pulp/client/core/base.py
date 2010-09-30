# -*- coding: utf-8 -*-

# Copyright © 2010 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.

import os
import sys
from gettext import gettext as _
from optparse import OptionParser, SUPPRESS_USAGE

from pulp.client import auth_utils
from pulp.client.config import Config
from pulp.client.connection import RestlibException
from pulp.client.logutil import getLogger


_cfg = Config()
_log = getLogger(__name__)

# output formatting -----------------------------------------------------------

_header_width = 45
_header_border = '+------------------------------------------+'

def print_header(*lines):
    padding = 0
    print _header_border
    for line in lines:
        if len(line) < _header_width:
            padding = ((_header_width - len(line)) / 2) - 1
        print ' ' * padding, line
    print _header_border

# system exit -----------------------------------------------------------------

def system_exit(code, msgs=None):
    """
    Exit with a code and optional message(s). Saved a few lines of code.
    @type code: int
    @param code: code to return
    @type msgs: str or list or tuple of str's
    @param msgs: messages to display
    """
    assert msgs is None or isinstance(msgs, (basestring, list, tuple))
    if msgs:
        if isinstance(msgs, basestring):
            msgs = (msgs,)
        for msg in msgs:
            print >> sys.stderr, msg
    sys.exit(code)

systemExit = system_exit

# base command class ---------------------------------------------------------

class Command(object):

    name = None
    _default_actions = ()

    def __init__(self, actions=_default_actions, action_state={}):
        self.actions = actions
        self.action_state = action_state
        # options and arguments
        self.parser = OptionParser(usage=self.usage())
        self.parser.disable_interspersed_args()
        # credentials
        self.username = None
        self.password = None
        self.cert_file = None
        self.key_file = None

    # attributes

    def usage(self):
        lines = ['Usage: %s <action> <options>' % self.name,
                 'Supported Actions:']
        for name in self.actions:
            action = getattr(self, name, None)
            plug = action.plug if action is not None else 'no description'
            lines.append('\t%-14s %-25s' % (name, plug))
        return '\n'.join(lines)

    def short_description(self):
        raise NotImplementedError('Base class method called')

    def long_description(self):
        raise NotImplementedError('Base class method called')

    def setup_credentials(self, username, password, cert_file, key_file):
        self.username = username
        self.password = password
        files = auth_utils.admin_cert_paths()
        cert_file = cert_file or files[0]
        key_file = key_file or files[1]
        if os.access(cert_file, os.F_OK | os.R_OK):
            self.cert_file = cert_file
        else:
            self.parser.error(_('error: cannot read cert file: %s') % cert_file)
        if os.access(key_file, os.F_OK | os.R_OK):
            self.key_file = key_file
        else:
            self.parser.error(_('error: cannot read key file: %s') % key_file)

    # main

    def get_action(self, name):
        if name not in self.actions or not hasattr(self, name):
            return None
        return getattr(self, name)

    def setup_action_connections(self, action):
        connections = action.connections()
        for name, cls in connections.items():
            connection = cls(host=_cfg.server.host or 'localhost',
                             port=_cfg.server.port or 443,
                             username=self.username,
                             password=self.password,
                             cert_file=self.cert_file,
                             key_file=self.key_file)
            setattr(action, name, connection)

    def main(self, args):
        if not args:
            self.parser.error(_('no action given: please see --help'))
        self.parser.parse_args(args)
        action = self.get_action(args[0])
        if action is None:
            self.parser.error(_('invalid action: please see --help'))
        if self.action_state:
            action.set_state(**self.action_state)
        self.setup_action_connections(action)
        action.main(args[1:])


BaseCore = Command

# base action class -------------------------------------------------

class Action(object):

    name = None
    plug = None
    description = None

    def __init__(self):
        self.parser = OptionParser(usage=SUPPRESS_USAGE)
        self.opts = None
        self.args = None

    def set_state(self, **kwargs):
        self.__dict__.update(kwargs)

    def connections(self):
        return {}

    def setup_parser(self):
        pass

    def parse_args(self):
        return self.parser.parse_args(self.args)

    def setup_server(self):
        raise NotImplementedError('Base class method called')

    def run(self):
        raise NotImplementedError('Base class method called')

    def get_required_option(self, opt):
        value = getattr(self.opts, opt)
        if value is None:
            self.parser.error(_('option %s is required; please see --help') % opt)
        return value

    def main(self, args):
        self.setup_parser()
        self.opts, self.args = self.parse_args(args)
        try:
            self.setup_server()
            self.run()
        except RestlibException, re:
            _log.error("error: %s" % re)
            system_exit(re.code, _('error: operation failed: ') + re.msg)
        except Exception, e:
            _log.error("error: %s" % e)
            raise
