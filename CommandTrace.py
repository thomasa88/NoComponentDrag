#Author-Thomas Axelsson
#Description-Traces Command calls

# This file is part of AnyShortcut, a Fusion 360 add-in for assigning
# shortcuts to the last run commands.
#
# Copyright (c) 2020 Thomas Axelsson
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import adsk.core, adsk.fusion, adsk.cam, traceback

from collections import deque
import math
import os
import operator
import time

NAME = 'CommandTrace'
FILE_DIR = os.path.dirname(os.path.realpath(__file__))

# Import relative path to avoid namespace pollution
from .thomasa88lib import utils
from .thomasa88lib import events
from .thomasa88lib import manifest
from .thomasa88lib import error
from .thomasa88lib import timeline

# Force modules to be fresh during development
import importlib
importlib.reload(thomasa88lib.utils)
importlib.reload(thomasa88lib.events)
importlib.reload(thomasa88lib.manifest)
importlib.reload(thomasa88lib.error)
importlib.reload(thomasa88lib.timeline)


app_ = None
ui_ = None
error_catcher_ = thomasa88lib.error.ErrorCatcher()
events_manager_ = thomasa88lib.events.EventsManager(error_catcher_)
manifest_ = thomasa88lib.manifest.read()

def command_starting_handler(args: adsk.core.ApplicationCommandEventArgs):
    print("START: ", args.commandId)
    if args.commandId == 'FusionDragComponentsCommand':
        args.isCanceled = True

def command_created_handler(args: adsk.core.ApplicationCommandEventArgs):
    print("CREATE:", args.commandId)

def command_terminated_handler(args: adsk.core.ApplicationCommandEventArgs):
    print("TERM:  ", args.commandId, args.terminationReason)

def run(context):
    global app_
    global ui_
    with error_catcher_:
        app_ = adsk.core.Application.get()
        ui_ = app_.userInterface

        events_manager_.add_handler(ui_.commandStarting, callback=command_starting_handler)
        events_manager_.add_handler(ui_.commandCreated, callback=command_created_handler)
        events_manager_.add_handler(ui_.commandTerminated, callback=command_terminated_handler)

def stop(context):
    with error_catcher_:
        events_manager_.clean_up()
